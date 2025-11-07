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
    as PDF using the provided JSON data (supports two-team comparison).
    """

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title="Process Benchmark Report")

    styles = getSampleStyleSheet()
    normal_style = ParagraphStyle(
        'NormalStyle', parent=styles['Normal'], fontSize=10, textColor=colors.black, leading=14
    )
    header_style = ParagraphStyle(
        'HeaderStyle', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#1E88E5')
    )
    section_title_style = ParagraphStyle(
        'SectionTitle', parent=styles['Heading3'], fontSize=11, textColor=colors.HexColor('#0D47A1')
    )

    elements = []

    # --- Title Section ---
    elements.append(Paragraph("Process Benchmark Report (Loops, Bottlenecks, Dropouts)", header_style))
    elements.append(Paragraph("Generated via AI Ninjas Process Mining Suite", normal_style))
    elements.append(Spacer(1, 10))

    # --- Executive Summary ---
    elements.append(Paragraph("<b>Executive Summary</b>", header_style))
    elements.append(Paragraph(data.get("Executive_Summary", "No summary available."), normal_style))
    elements.append(Spacer(1, 12))

    # --- KPI Table ---
    kpi_data = data.get("KPI_Benchmark", [])

    if kpi_data:
        first_item = kpi_data[0]
        team1_label = first_item.get("Team_1_Label", "Team 1")
        team2_label = first_item.get("Team_2_Label", "Team 2")

        elements.append(Paragraph("<b>KPI Benchmark Table</b>", header_style))

        # Create table header
        kpi_table_data = [[
            Paragraph("<b>Metric</b>", normal_style),
            Paragraph(f"<b>{team1_label}</b>", normal_style),
            Paragraph(f"<b>{team2_label}</b>", normal_style),
            Paragraph("<b>Status</b>", normal_style)
        ]]

        # Add rows with Paragraphs for wrapping
        for item in kpi_data:
            metric = Paragraph(str(item.get("Metric", "")), normal_style)
            team1_value = Paragraph(str(item.get("Team_1_Value", "")), normal_style)
            team2_value = Paragraph(str(item.get("Team_2_Value", "")), normal_style)
            status = Paragraph(str(item.get("Status", "")), normal_style)

            kpi_table_data.append([metric, team1_value, team2_value, status])

        # Adjusted column widths for wrapping balance
        table = Table(kpi_table_data, colWidths=[130, 100, 100, 140])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E88E5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 20))

    # --- Analysis Sections ---
    analysis = data.get("Analysis_Report", {})
    if analysis:
        elements.append(Paragraph("<b>Analysis Report</b>", header_style))

        for section, content in analysis.items():
            title = section.replace("_", " ").title()
            text = list(content.values())[0] if isinstance(content, dict) and content else "No content available."
            elements.append(Spacer(1, 8))
            elements.append(Paragraph(f"<b>{title}</b>", section_title_style))
            elements.append(Paragraph(text, normal_style))
            elements.append(Spacer(1, 5))

    doc.build(elements)
    buffer.seek(0)
    return buffer