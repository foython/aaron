from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from io import BytesIO
from django.http import FileResponse

def generate_kpi_benchmark_pdf(data):
    """
    Generate a Process Benchmark Report (Loops, Bottlenecks, Dropouts)
    as PDF using the provided JSON data.
    """

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title="Process Benchmark Report")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#FFFFFF'), spaceAfter=12
    )
    normal_style = ParagraphStyle(
        'NormalStyle', parent=styles['Normal'], fontSize=10, textColor=colors.black, leading=14
    )
    header_style = ParagraphStyle(
        'HeaderStyle', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#1E88E5')
    )

    elements = []

    # --- Title Section ---
    elements.append(Paragraph("Process Benchmark Report (Loops, Bottlenecks, Dropouts)", header_style))
    elements.append(Paragraph("Generated via AI Ninjas Process Mining Suite", normal_style))
    elements.append(Spacer(1, 10))

    # --- Executive Summary ---
    elements.append(Paragraph("<b>Executive Summary</b>", header_style))
    elements.append(Paragraph(data["Executive_Summary"], normal_style))
    elements.append(Spacer(1, 12))

    # --- KPI Table ---
    elements.append(Paragraph("<b>KPI Benchmark Table</b>", header_style))
    kpi_table_data = [["Metric", "Current Value", "Target Value", "Status"]]
    for item in data["KPI_Benchmark"]:
        kpi_table_data.append([
            item["Metric"],
            item["Current Value"],
            item["Target Value"],
            item["Status"],
        ])

    table = Table(kpi_table_data, colWidths=[140, 120, 100, 80])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E88E5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 15))

    # --- Analysis Sections ---
    elements.append(Paragraph("<b>Analysis Report</b>", header_style))
    analysis = data["Analysis_Report"]

    for section, content in analysis.items():
        title = section.replace("_", " ").title()
        text = list(content.values())[0]
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(f"<b>{title}</b>", ParagraphStyle(name="SectionTitle", fontSize=11, textColor=colors.HexColor("#0D47A1"))))
        elements.append(Paragraph(text, normal_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer
