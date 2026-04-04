# 🎓 Bot de Certificados Canva

Bot de Telegram que genera certificados individuales a través de la API de **Canva Connect**.

## Flujo de uso

1. **Autenticar Canva**
   ```bash
   python scripts/auth_cli.py
   ```

2. **Ejecutar el bot**
   ```bash
   python bot.py
   ```

3. **Generar certificados desde Telegram**
   - `/certificado` — inicia el flujo (pide nombre y tipo)
   - `/cancel` — cancela la operación en curso

## Configuración

### Dependencias
```bash
pip install -r requirements.txt
```

### Variables de entorno (`.env`)
```env
# Canva OAuth
CANVA_CLIENT_ID=
CANVA_CLIENT_SECRET=

# Templates
TEMPLATE_ID_REAL=
TEMPLATE_ID_PASE=

# App
TOKEN_STORE_PATH=./token_store.json

# Telegram
TELEGRAM_BOT_TOKEN=
```

### Token de Canva
Copia el archivo `token_store.json` obtenido con `auth_cli.py` en la raíz del proyecto. El módulo gestiona la autenticación y el refresco de tokens automáticamente.

## Prueba manual (sin bot)
```bash
python scripts/run_certificador.py "Juan Pérez" "real"
```

## Características

- Generación individual de certificados en formato **PNG**
- Envío automático al chat de Telegram como documento
- Polling con backoff exponencial y jitter
- Reintentos automáticos ante errores temporales
- Respeto a cuotas de API (429 Retry-After)
- Persistencia atómica de tokens OAuth
- Logging con rotación en `logs/certificador.log`

---
© Proyecto Canva Connect – Integración de Automatización
