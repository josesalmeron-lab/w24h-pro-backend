from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber, io, os, pymysql, json
from datetime import datetime
from parser import extract_and_calculate
from database import get_db

app = FastAPI(title="W24H PRO | Producción F&B")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    """Endpoint para UptimeRobot - mantiene el servicio activo"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), db = Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Solo se aceptan archivos PDF")
        
    with pdfplumber.open(file.file) as pdf:
        text = "\n".join([page.extract_text() or "" for page in pdf.pages])
        
    data = extract_and_calculate(text)
    cur = db.cursor()
    
    try:
        cur.execute("START TRANSACTION")
        cur.execute("INSERT INTO events (code, name, service_date, salon) VALUES (%s, %s, %s, %s)",
                    (data["event"]["code"], data["event"]["name"], data["event"]["service_date"], data["event"]["salon"]))
        event_id = cur.lastrowid
        
        cur.execute("INSERT INTO pax (event_id, adults, children) VALUES (%s, %s, %s)",
                    (event_id, data["event"]["adults"], data["event"]["children"]))
        
        for s in data["schedules"]:
            cur.execute("INSERT INTO schedules (event_id, type, start_time, end_time) VALUES (%s, %s, %s, %s)",
                        (event_id, s["type"], s["start"], s["end"]))
                        
        for t, p in data["menus"].items():
            cur.execute("INSERT INTO menus (event_id, type, price_per_pax) VALUES (%s, %s, %s)", (event_id, t, p))
            
        for item in data["production"]:
            cur.execute("""INSERT INTO production_items (event_id, station, item_name, base_qty, pax_factor, notes) 
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (event_id, item["station"], item["item_name"], item["base_qty"], item["pax_factor"], item["notes"]))
                        
        cur.execute("INSERT INTO montage (event_id, area, details, table_map) VALUES (%s, %s, %s, %s)",
                    (event_id, data["montage"]["area"], data["montage"]["details"], json.dumps(data["montage"]["table_map"])))
                    
        cur.execute("INSERT INTO finance (event_id, `signal`, remaining, contact_phone) VALUES (%s, %s, %s, %s)",
                    (event_id, data["finance"]["signal"], data["finance"]["remaining"], data["finance"]["contact_phone"]))
        db.commit()
        return {"event_id": event_id, "status": "success", "preview": data}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error DB: {str(e)}")

@app.get("/events/{event_id}/{dept}")
def get_dept_data(event_id: int, dept: str, db = Depends(get_db)):
    dept_map = {
        "cocina_frios": "CÓCTEL%", "cocina_calientes": "CALIENTES%", "pasteleria": "PASTELERÍA%",
        "bodega": "BODEGA%", "sala": "MONTAJE%", "infantil": "INFANTIL%", "primeros": "PRIMEROS%"
    }
    pattern = dept_map.get(dept)
    if not pattern: return {"error": "Departamento no válido"}
    
    cur = db.cursor()
    cur.execute("SELECT * FROM production_items WHERE event_id=%s AND station LIKE %s ORDER BY station, item_name", (event_id, pattern))
    items = cur.fetchall()
    
    cur.execute("SELECT details, table_map FROM montage WHERE event_id=%s", (event_id,))
    montage = cur.fetchone()
    
    return {"items": items, "montage": montage["details"] if montage else "", "tables": montage["table_map"] if montage else "[]"}

@app.post("/export/{event_id}/{dept}")
def export_excel(event_id: int, dept: str, db = Depends(get_db)):
    res = get_dept_data(event_id, dept, db)
    if "error" in res: raise HTTPException(400, res["error"])
    
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Producción"
    
    # Headers
    ws.append(["Estación", "Item", "Base/pax", "Pax", "TOTAL", "Notas"])
    
    # Datos
    for item in res.get("items", []):
        ws.append([
            item.get("station", ""),
            item.get("item_name", ""),
            item.get("base_qty", ""),
            item.get("pax_factor", ""),
            item.get("calc_qty", ""),
            item.get("notes", "")
        ])
    
    # Montaje si existe
    if res.get("montage"):
        ws.append(["📋 MONTAJE", "", "", "", "", res["montage"]])
    
    # Tablas si existen
    tables = res.get("tables", "[]")
    if isinstance(tables, str):
        try:
            tables = json.loads(tables)
        except:
            tables = []
    if tables:
        ws.append(["🪑 MESETAS", "", "", "", "", ", ".join(tables)])
    
    # Guardar en buffer
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    return StreamingResponse(
        buf, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={dept}_{event_id}.xlsx"}
    )
