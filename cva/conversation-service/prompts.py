"""Prompt helpers for tone control, greetings, and bilingual rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


TONE_PRESETS: Dict[str, Dict[str, Dict[str, str]]] = {
    "friendly": {
        "en": {"header": "😊 Friendly assistant", "greeting": "Hi there!"},
        "es": {"header": "😊 Asistente amable", "greeting": "¡Hola!"},
    },
    "professional": {
        "en": {"header": "📘 Professional assistant", "greeting": "Good day."},
        "es": {"header": "📘 Asistente profesional", "greeting": "Buen día."},
    },
    "urgent": {
        "en": {"header": "⏱️ Urgent update", "greeting": "Please listen carefully."},
        "es": {"header": "⏱️ Actualización urgente", "greeting": "Por favor escuche con atención."},
    },
    "neutral": {
        "en": {"header": "Assistant", "greeting": "Hello."},
        "es": {"header": "Asistente", "greeting": "Hola."},
    },
}


@dataclass(frozen=True)
class PromptBundle:
    """Collection of prompt fragments used to shape responses."""

    primary_language: str
    tone_header_en: str
    tone_header_es: str
    greeting_en: str
    greeting_es: str
    english: str
    spanish: str


def _translate_to_spanish(text: str) -> str:
    """Naive English to Spanish translation for demo purposes."""

    lexicon = {
        "a": "una",
        "activate": "activar",
        "also": "también",
        "arrange": "organizar",
        "appointment": "cita",
        "are": "están",
        "booking": "opciones de reserva",
        "address": "dirección",
        "but": "pero",
        "calendar": "calendario",
        "can": "puedo",
        "caller": "cliente",
        "confirmation": "confirmación",
        "context": "contexto",
        "couldn't": "no pude",
        "details": "detalles",
        "for": "para",
        "found": "encontré",
        "here": "Aquí",
        "here's": "Aquí está",
        "i": "Yo",
        "i'm": "Estoy",
        "i've": "He",
        "if": "si",
        "is": "está",
        "installation": "instalación",
        "know": "saber",
        "let": "avísame",
        "message": "mensaje",
        "me": "me",
        "needed": "es necesario",
        "next": "la próxima",
        "note": "nota",
        "notification": "notificación",
        "now": "ahora",
        "options": "opciones",
        "our": "nuestro",
        "please": "Por favor",
        "queued": "programado",
        "receive": "recibirá",
        "right": "ahora",
        "shortly": "pronto",
        "slots": "horarios",
        "soon": "pronto",
        "service": "servicio",
        "taking": "tomando",
        "team": "equipo",
        "temporarily": "temporalmente",
        "the": "las",
        "tools": "herramientas",
        "to": "para",
        "unavailable": "no disponible",
        "up": "seguimiento",
        "via": "por",
        "water": "agua",
        "week": "semana",
        "we'll": "nosotros",
        "what": "lo que",
        "you": "usted",
        "you'll": "Recibirá",
    }
    phrase_overrides = {
        "follow up": "dar seguimiento",
        "job location": "dirección del trabajo",
        "service summary": "resumen del servicio",
        "we'll see you": "nos vemos",
    }
    working_text = text.lower()
    for phrase, replacement in phrase_overrides.items():
        working_text = working_text.replace(phrase, replacement)
    translated = []
    for token in working_text.replace(".", "").split():
        word = token.lower()
        translated.append(lexicon.get(word, token))
    return " ".join(translated)


def build_prompt(
    tone: str,
    english_text: str,
    *,
    bilingual: bool = True,
    primary_language: str = "en",
) -> PromptBundle:
    """Render the tone header, greeting, and bilingual body."""

    preset = TONE_PRESETS.get(tone.lower(), TONE_PRESETS["neutral"])
    primary_language = primary_language if primary_language in {"en", "es"} else "en"
    if bilingual or primary_language == "es":
        spanish_text = _translate_to_spanish(english_text)
    else:
        spanish_text = ""
    return PromptBundle(
        primary_language=primary_language,
        tone_header_en=preset["en"]["header"],
        tone_header_es=preset["es"]["header"],
        greeting_en=preset["en"]["greeting"],
        greeting_es=preset["es"]["greeting"],
        english=english_text,
        spanish=spanish_text,
    )


def format_bilingual_message(
    bundle: PromptBundle,
    *,
    bilingual: bool = True,
    primary_language: str = "en",
    include_greeting: bool = False,
) -> str:
    """Combine prompt fragments into a human readable response."""

    primary_language = primary_language if primary_language in {"en", "es"} else "en"
    secondary_language = "es" if primary_language == "en" else "en"

    def compose(language: str) -> str:
        header = bundle.tone_header_es if language == "es" else bundle.tone_header_en
        greeting = bundle.greeting_es if language == "es" else bundle.greeting_en
        body = bundle.spanish if language == "es" and bundle.spanish else bundle.english
        lines = [header]
        if include_greeting and greeting:
            lines.append(greeting)
        lines.append(body if body else bundle.english)
        return "\n".join(lines)

    primary_text = compose(primary_language)
    if bilingual and (bundle.spanish or primary_language == "es"):
        secondary_text = compose(secondary_language)
        return f"{primary_text}\n\n{secondary_text}"
    return primary_text
