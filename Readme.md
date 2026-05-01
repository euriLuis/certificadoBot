# Bot de Certificados Canva

Bot de Telegram que genera certificados individuales a traves de la API de Canva Connect y los envia por Telegram y por correo.

## Tipos de certificado soportados

- `real`
- `pase de fase` o `pase`
- `elite`

## Flujo de uso

1. Autenticar Canva

```bash
python scripts/auth_cli.py
```

2. Ejecutar el bot

```bash
python bot.py
```

3. Generar certificados desde Telegram

- `/certificado` inicia el flujo
- `/cancel` cancela la operacion en curso
- El bot pide nombre, tipo y luego el email de destino
- El bot valida el tipo de certificado y el formato del email antes de continuar
- Si falla el envio por correo, el flujo permite reintentar con otro email sin regenerar el certificado

## Configuracion

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
TEMPLATE_ID_ELITE=

# App
TOKEN_STORE_PATH=./token_store.json

# Telegram
TELEGRAM_BOT_TOKEN=

# Resend
RESEND_API_KEY=
RESEND_FROM_EMAIL=Qvafunded <certificados@tu-dominio.com>
```

### Template `elite`

El nuevo certificado `elite` requiere definir `TEMPLATE_ID_ELITE` en tu `.env`.
Si ese valor falta, el bot detecta la configuracion incompleta y corta el flujo con un mensaje claro en lugar de fallar tarde dentro de Canva.
Para la plantilla `EAHBZ9RY-qU`, la API de Canva expone actualmente estos campos autofillables:

- `fecha` (`text`)
- `Nombre` (`text`)

La integracion principal del bot ya quedo configurada con el mapeo correcto para cada tipo y no consulta el dataset en cada generacion.

Configuracion fija actual:

- `real`: `nombre` y `fecha`
- `pase de fase`: `nombre` y `fecha`
- `elite`: `Nombre` y `fecha`

### Token de Canva

Copia el archivo `token_store.json` obtenido con `auth_cli.py` en la raiz del proyecto. El modulo gestiona la autenticacion y el refresco de tokens automaticamente.

## Prueba manual (sin bot)

```bash
python scripts/run_certificador.py "Juan Perez" "elite"
```

## Prueba de autofill separada

```bash
python scripts/test_autofill_template.py
```

Ese script:

- consulta metadata y dataset del template
- muestra los campos autofillables reales
- resuelve el mapeo semantico (`nombre`, `fecha`) hacia las claves exactas del template
- ejecuta una prueba real de `POST /autofills`
- espera el resultado y devuelve el `design_id`

Ejemplo validado sobre la plantilla `EAHBZ9RY-qU`:

- dataset detectado: `fecha`, `Nombre`
- mapeo resuelto: `nombre -> Nombre`, `fecha -> fecha`
- autofill: exitoso

## Directorios de salida

- `certificados_real/`
- `pases_de_fase/`
- `certificados_elite/`

## Correo por tipo de certificado

El envio por Resend ajusta asunto y mensaje principal segun el tipo:

- `real`: asunto y texto orientados al pase a real
- `pase de fase`: asunto y texto orientados al avance de fase
- `elite`: asunto y cuerpo especificos para el reconocimiento elite

## Mejoras de robustez en el flujo del bot

- Validacion mas estricta de nombre y email
- Reentrada segura al flujo con `/certificado`
- Limpieza controlada del estado conversacional
- Modo secuencial para evitar conflictos en `ConversationHandler`
- Manejo global de errores del dispatcher
- Reintento del paso de email sin perder el certificado ya generado
- Mensajes de error mas claros cuando falta configuracion o el archivo generado no aparece
- Mapeo fijo de claves autofill por tipo ya validado contra Canva

## Mensajes del bot en Telegram

El bot ahora informa con mas claridad:

- el flujo exacto que seguira al iniciar
- los tipos soportados cuando pide el tipo de certificado
- el tipo y destinatario mientras genera y envia
- cuando un correo falla pero el certificado sigue disponible para reintentar

## Caracteristicas

- Generacion individual de certificados en formato PNG
- Envio automatico al chat de Telegram como documento
- Envio por correo mediante Resend
- Polling con backoff exponencial y jitter
- Reintentos automaticos ante errores temporales
- Respeto a cuotas de API (429 Retry-After)
- Persistencia atomica de tokens OAuth
- Logging con rotacion en `logs/certificador.log`

---

Proyecto Canva Connect - Integracion de Automatizacion
