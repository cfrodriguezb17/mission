"""PDF desde una instantánea autorizada; no consulta proveedores externos."""
from html import escape
from io import BytesIO
from pathlib import Path

import reportlab

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_FOLDER = Path(reportlab.__file__).parent / "fonts"
for name, filename in [("DPSans", "Vera.ttf"), ("DPSans-Bold", "VeraBd.ttf"),
                       ("DPSans-Italic", "VeraIt.ttf"), ("DPSans-BoldItalic", "VeraBI.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONT_FOLDER / filename)))
pdfmetrics.registerFontFamily("DPSans", normal="DPSans", bold="DPSans-Bold",
                              italic="DPSans-Italic", boldItalic="DPSans-BoldItalic")


def generar_pdf(*, portafolio, posiciones, resumen, riesgos, fecha):
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        if isinstance(style, ParagraphStyle):
            style.fontName = "DPSans-Bold" if "Bold" in style.fontName else "DPSans"
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 12
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 16
    styles["Heading2"].spaceBefore = 10
    styles["Heading2"].spaceAfter = 6
    styles.add(ParagraphStyle("Celda", fontName="DPSans", fontSize=8, leading=11, spaceAfter=0,
                              splitLongWords=True))
    styles.add(ParagraphStyle("Numero", parent=styles["Celda"], alignment=TA_RIGHT))
    styles["Title"].textColor = colors.HexColor("#15324f")
    styles["Heading2"].textColor = colors.HexColor("#15324f")
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=42, leftMargin=42,
                                 topMargin=44, bottomMargin=40, title="Reporte de portafolio DataPulse",
                                 author="DataPulse Latam")

    def paragraph(value, style="Celda"):
        return Paragraph(escape(str(value if value is not None else "Sin datos")), styles[style])

    def table(rows, widths):
        result = LongTable(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edf6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#bdcddd")),
        ]))
        return result

    def money(value):
        from decimal import Decimal
        return f"{Decimal(value):,.2f} USD"

    story = [paragraph("DataPulse Latam", "Title"), paragraph(portafolio.nombre, "Heading1"),
             paragraph(f"Propietario: {portafolio.usuario.nombre_completo} | Versión: {portafolio.version}"),
             paragraph(f"Generado: {fecha.strftime('%Y-%m-%d %H:%M UTC')} | "
                       f"Visibilidad: {'Público' if portafolio.es_publico else 'Privado'}"), Spacer(1, 12)]
    if portafolio.descripcion:
        story.extend([paragraph(portafolio.descripcion, "BodyText"), Spacer(1, 12)])
    story.extend([paragraph("Resumen de posiciones activas", "Heading2"),
                  table([[paragraph("Concepto"), paragraph("Valor")],
                         [paragraph("Capital invertido"), paragraph(money(resumen["total_invertido_usd"]))],
                         [paragraph("Posiciones activas"), paragraph(resumen["posiciones_activas"])],
                         [paragraph("IRPC ponderado (0-100)"), paragraph(resumen["riesgo_promedio_ponderado"])],
                         [paragraph("Capital sin índice de riesgo"), paragraph(money(resumen["monto_sin_riesgo_usd"]))]],
                        [260, 251]), Spacer(1, 12)])
    if resumen["riesgo_incompleto"]:
        story.append(paragraph("Advertencia: el promedio considera únicamente el capital con índice disponible. "
                               "Países sin índice: " + ", ".join(resumen["paises_sin_riesgo"]), "BodyText"))
    for key, title in [("distribucion_por_pais", "Distribución por país"),
                       ("distribucion_por_tipo_activo", "Distribución por tipo de activo"),
                       ("distribucion_por_riesgo", "Distribución por nivel de riesgo")]:
        story.append(paragraph(title, "Heading2"))
        rows = [[paragraph("Categoría"), paragraph("Capital activo"), paragraph("Porcentaje")]]
        rows += [[paragraph(row["codigo"]), paragraph(money(row["monto_usd"]), "Numero"),
                  paragraph(row["porcentaje"] + " %", "Numero")] for row in resumen[key]]
        story.append(table(rows, [231, 180, 100]) if len(rows) > 1 else paragraph("Sin posiciones activas."))
    story.append(paragraph("Posiciones (activas y cerradas)", "Heading2"))
    rows = [[paragraph(value) for value in ["País", "Tipo de activo", "Monto USD", "Entrada", "Salida", "IRPC / nivel"]]]
    for position in posiciones:
        risk = riesgos.get(position.pais_id)
        rows.append([paragraph(position.pais.nombre), paragraph(position.tipo_activo),
                     paragraph(f"{position.monto_inversion_usd:,.2f}", "Numero"), paragraph(position.fecha_entrada),
                     paragraph(position.fecha_salida or "Activa"),
                     paragraph(f"{risk.indice_compuesto} / {risk.nivel_riesgo}" if risk else "Sin datos")])
    story.append(table(rows, [70, 115, 95, 65, 65, 101]) if len(rows) > 1 else paragraph("Sin posiciones."))
    for position in posiciones:
        if position.notas:
            story.append(paragraph(f"Nota de posición {position.pk}: {position.notas}", "BodyText"))
    story.append(paragraph("Evidencia de riesgo", "Heading2"))
    for code, risk in sorted(riesgos.items()):
        flags = []
        if risk.detalle_calculo.get("datos_parciales"):
            flags.append("datos incompletos")
        if risk.detalle_calculo.get("contiene_simulaciones"):
            flags.append("incluye datos simulados")
        story.append(paragraph(
            f"{code}: económico {risk.score_economico}, cambiario {risk.score_cambiario}, "
            f"estabilidad {risk.score_estabilidad}; IRPC {risk.indice_compuesto}. "
            f"Cálculo {risk.fecha_calculo.strftime('%Y-%m-%d %H:%M UTC')}; fórmula {risk.version_formula}. "
            + ("; ".join(flags) if flags else ""), "BodyText"))
    story.extend([Spacer(1, 12), paragraph(
        "Un IRPC más alto representa menor riesgo. El índice describe la evidencia disponible; "
        "los datos simulados se identifican para demostración.", "BodyText")])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("DPSans", 8)
        canvas.setFillColor(colors.HexColor("#526479"))
        canvas.drawString(42, 25, "DataPulse Latam | Reporte de portafolio")
        canvas.drawRightString(A4[0] - 42, 25, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
