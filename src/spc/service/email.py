"""Envío de correo para el restablecimiento de contraseña.

Usa **solo la biblioteca estándar** (``smtplib`` + ``email.message``), mismo criterio de
cero dependencias del resto del proyecto (ADR-0014). El servidor SMTP se configura por
entorno (``SPC_SMTP_*``, ver :mod:`spc.config`).

**Modo desarrollo:** si no hay ``SPC_SMTP_HOST`` configurado, no se intenta conectar a
ningún servidor: se **registra el enlace en el log** y se devuelve ``False``. Así el flujo
de reset es probable de punta a punta en local sin un servidor de correo real, y nunca
rompe la petición.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from spc.config import app_base_url, smtp_config, smtp_habilitado
from spc.utils.logging import get_logger

log = get_logger("service.email")


def construir_enlace_reset(token: str) -> str:
    """Construye el enlace del frontend para restablecer la contraseña con ``token``."""
    return f"{app_base_url()}/reset?token={token}"


def _cuerpo_reset(enlace: str) -> tuple[str, str]:
    """Devuelve (texto_plano, html) del correo de restablecimiento."""
    texto = (
        "Recibimos una solicitud para restablecer tu contraseña en SPC.\n\n"
        f"Abre este enlace para elegir una nueva contraseña (caduca pronto):\n{enlace}\n\n"
        "Si no fuiste tú, ignora este correo: tu contraseña no cambiará."
    )
    html = (
        "<p>Recibimos una solicitud para restablecer tu contraseña en <b>SPC</b>.</p>"
        f'<p><a href="{enlace}">Elegir una nueva contraseña</a> (el enlace caduca pronto).</p>'
        "<p>Si no fuiste tú, ignora este correo: tu contraseña no cambiará.</p>"
    )
    return texto, html


def enviar_email_reset(destinatario: str, token: str) -> bool:
    """Envía el correo de restablecimiento. Devuelve ``True`` si se envió por SMTP.

    Nunca lanza: un fallo de correo se registra y devuelve ``False`` (el endpoint responde
    genérico igual, para no filtrar si la cuenta existe). Sin SMTP configurado, registra el
    enlace en el log (modo desarrollo) y devuelve ``False``.
    """
    enlace = construir_enlace_reset(token)
    if not smtp_habilitado():
        log.warning(
            "SMTP no configurado: enlace de reset para %s (solo log, no se envió): %s",
            destinatario,
            enlace,
        )
        return False

    cfg = smtp_config()
    texto, html = _cuerpo_reset(enlace)
    msg = EmailMessage()
    msg["Subject"] = "Restablece tu contraseña — SPC"
    msg["From"] = str(cfg["remitente"])
    msg["To"] = destinatario
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(str(cfg["host"]), int(cfg["port"]), timeout=15) as smtp:
            smtp.starttls()
            if cfg["user"]:
                smtp.login(str(cfg["user"]), str(cfg["password"]))
            smtp.send_message(msg)
        log.info("Correo de restablecimiento enviado a %s", destinatario)
        return True
    except Exception as exc:  # noqa: BLE001 — un fallo de correo no debe romper el endpoint
        log.error("No se pudo enviar el correo de restablecimiento a %s: %s", destinatario, exc)
        return False
