from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import logging

# --------------------------------------------------
# Configuración de logs (esto es clave para Grafana)
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI()

templates = Jinja2Templates(directory="templates")


# -----------------------------
# Ruta principal (Login Page)
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# -----------------------------
# Ruta que genera error 500
# -----------------------------
@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    
    logger.info(f"Intento de login recibido para usuario: {username}")

    # 🔥 ERROR INTENCIONAL
    try:
        result = 10 / 0  # Esto genera ZeroDivisionError
        return {"message": "Nunca llegará aquí", "result": result}
    
    except Exception as e:
        logger.error("Error crítico en proceso de login", exc_info=True)
        raise e  # Esto dispara un HTTP 500