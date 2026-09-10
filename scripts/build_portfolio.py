"""Build the four-page English project portfolio with clickable evidence links."""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/pdf/QihuiPan_Incident_Assistant_Portfolio.pdf"
REPO = "https://github.com/QihuiPan/llm-production-incident-assistant"
DEMO = "https://llm-incident-assistant.onrender.com/"
CI = f"{REPO}/actions/runs/34044524392"
IMAGES = f"{REPO}/actions/runs/34044698810"
WIDTH, HEIGHT = A4
MARGIN = 42
CONTENT = WIDTH - 2 * MARGIN
INK = "142339"
MUTED = "53647B"
BLUE = "2855DC"
PALE = "EEF3FA"
LINE = "D9E2F0"
WHITE = "FFFFFF"
TEAL = "087D70"


def register_fonts() -> tuple[str, str, str]:
    """Use installed readable fonts, with standard PDF fonts as a fallback."""

    choices = [
        (
            Path("C:/Windows/Fonts"),
            ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu"),
            ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSansMono.ttf"),
        ),
    ]
    names = ("PortfolioRegular", "PortfolioBold", "PortfolioMono")
    for folder, files in choices:
        if all((folder / item).exists() for item in files):
            for name, filename in zip(names, files, strict=True):
                pdfmetrics.registerFont(TTFont(name, str(folder / filename)))
            pdfmetrics.registerFontFamily(names[0], normal=names[0], bold=names[1])
            return names
    return "Helvetica", "Helvetica-Bold", "Courier"


class Portfolio:
    """Draw deliberate page layouts using top-based coordinates."""

    def __init__(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.pdf = canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
        self.pdf.setTitle("Qihui Pan | LLM Production Incident Assistant Portfolio")
        self.pdf.setAuthor("Qihui Pan")
        self.pdf.setSubject("Engineering portfolio and project case study, v2.2.0")
        self.regular, self.bold, self.mono = register_fonts()

    def rect(self, x: float, top: float, w: float, h: float, color: str) -> None:
        self.pdf.setFillColor(HexColor(f"#{color}"))
        self.pdf.rect(x, HEIGHT - top - h, w, h, stroke=0, fill=1)

    def text(
        self,
        value: str,
        x: float,
        top: float,
        width: float,
        size: float = 10.5,
        color: str = INK,
        bold: bool = False,
        leading: float | None = None,
    ) -> float:
        style = ParagraphStyle(
            "portfolio",
            fontName=self.bold if bold else self.regular,
            fontSize=size,
            leading=leading or size * 1.45,
            textColor=HexColor(f"#{color}"),
            alignment=TA_LEFT,
            splitLongWords=False,
        )
        paragraph = Paragraph(value, style)
        _, height = paragraph.wrap(width, HEIGHT)
        if top + height > HEIGHT - 32:
            raise ValueError(f"Text exceeds the page boundary: {value[:65]}")
        paragraph.drawOn(self.pdf, x, HEIGHT - top - height)
        return top + height

    def label(self, value: str, x: float, top: float, color: str = BLUE) -> None:
        self.pdf.setFillColor(HexColor(f"#{color}"))
        self.pdf.setFont(self.mono, 9)
        self.pdf.drawString(x, HEIGHT - top - 9, value.upper())

    def line(self, top: float, color: str = LINE) -> None:
        self.pdf.setStrokeColor(HexColor(f"#{color}"))
        self.pdf.setLineWidth(0.6)
        self.pdf.line(MARGIN, HEIGHT - top, WIDTH - MARGIN, HEIGHT - top)

    def footer(self, page: int) -> None:
        self.line(795)
        self.label("QIHUI PAN / ENGINEERING PORTFOLIO", MARGIN, 809, MUTED)
        self.label(f"{page:02d} / 04", WIDTH - 90, 809, MUTED)

    def new_page(self, page: int, section: str, title: str, deck: str) -> None:
        self.rect(0, 0, WIDTH, HEIGHT, WHITE)
        self.label("QIHUI PAN", MARGIN, 33, INK)
        self.label(section, WIDTH - 250, 33, MUTED)
        self.line(55)
        self.text(title, MARGIN, 75, CONTENT, 27, bold=True, leading=33)
        self.text(deck, MARGIN, 120, CONTENT, 11, MUTED)
        self.footer(page)

    def link_button(self, title: str, url: str, x: float, top: float, w: float) -> None:
        self.rect(x, top, w, 34, BLUE)
        self.text(title, x + 13, top + 8, w - 24, 10, WHITE, True)
        self.pdf.linkURL(url, (x, HEIGHT - top - 34, x + w, HEIGHT - top), relative=0)

    def cover(self) -> None:
        self.rect(0, 0, WIDTH, HEIGHT, WHITE)
        self.rect(0, 0, WIDTH, 470, INK)
        self.label("QIHUI PAN", MARGIN, 37, WHITE)
        self.label("ENGINEERING PORTFOLIO / 2026", 290, 37, "C4D3EA")
        self.rect(MARGIN, 105, 40, 4, "78A1FF")
        self.label("SELECTED PROJECT 01", MARGIN, 130, "A9C1FF")
        self.text(
            "LLM Production<br/>Incident Assistant",
            MARGIN,
            158,
            CONTENT,
            37,
            WHITE,
            True,
            44,
        )
        self.text(
            "From an alert to an<br/>evidence-backed investigation.",
            MARGIN,
            267,
            CONTENT,
            20,
            "D7E3FA",
            leading=28,
        )
        self.label("PYTHON / FASTAPI / REACT / POSTGRESQL", MARGIN, 340, "A9C1FF")
        self.line(373, "3A4960")
        for x, value, caption in [
            (MARGIN, "100", "synthetic benchmark cases"),
            (MARGIN + 175, "3", "prepared demo scenarios"),
            (MARGIN + 350, "v2.2.0", "verified release"),
        ]:
            self.text(value, x, 390, 160, 27, WHITE, True)
            self.text(caption, x, 431, 160, 9, "C4D3EA")

        self.label("THE CHALLENGE", MARGIN, 500)
        self.text("Make incident reasoning inspectable.", MARGIN, 521, CONTENT, 22, bold=True)
        self.text(
            "On-call engineers must connect alerts with runbooks, previous incidents, "
            "and telemetry. This project brings those sources into a single workspace "
            "and links preliminary hypotheses to versioned evidence, while the engineer "
            "retains control over tool execution.",
            MARGIN,
            564,
            CONTENT,
            11,
        )
        self.label("PROJECT SCOPE", MARGIN, 652)
        self.text(
            "Full-stack application, retrieval pipeline, tool controls, automated "
            "evaluation, and cloud delivery.",
            MARGIN,
            674,
            242,
            10.5,
        )
        self.label("DELIVERY", 316, 652)
        self.text(
            "Independent portfolio project.<br/>Public source and a keyless demo.<br/>"
            "Portfolio prepared September 11, 2026.",
            316,
            674,
            237,
            10.5,
        )
        self.link_button("Open live demo", DEMO, MARGIN, 748, 158)
        self.link_button("View source code", REPO, 212, 748, 158)
        self.footer(1)
        self.pdf.showPage()

    def product(self) -> None:
        self.new_page(
            2,
            "01 / PRODUCT EXPERIENCE",
            "A workflow an engineer can inspect.",
            "Choose an incident. Follow the evidence. Review the proposed next queries.",
        )
        screenshot = ROOT / "docs/assets/incident-assistant-workspace.png"
        image_top = 158
        image_height = 504
        self.rect(MARGIN, image_top, CONTENT, image_height, PALE)
        self.pdf.drawImage(
            str(screenshot),
            MARGIN,
            HEIGHT - image_top - image_height,
            width=CONTENT,
            height=image_height,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
        self.text(
            "Actual v2.2.0 entry workspace, captured during local browser verification. "
            "The public demo offers checkout, payments, and inventory scenarios.",
            MARGIN,
            674,
            CONTENT,
            9,
            MUTED,
        )
        self.line(716)
        for x, value, caption in [
            (MARGIN, "7 evidence items", "Versioned sources in the checkout smoke test"),
            (
                MARGIN + 177,
                "1 preliminary hypothesis",
                "Assessment remains subject to operator review",
            ),
            (MARGIN + 354, "3 pending queries", "Deployment, log, and metric investigation"),
        ]:
            self.text(value, x, 731, 157, 10.5, bold=True)
            self.text(caption, x, 750, 157, 8.5, MUTED)
        self.pdf.showPage()

    def architecture(self) -> None:
        self.new_page(
            3,
            "02 / ENGINEERING",
            "Grounding is a system concern.",
            "The API connects retrieval, structured composition, and controlled tool execution.",
        )
        rows = [
            (
                "01",
                "Capture context",
                "React + TypeScript",
                "Service, environment, alert, time window",
            ),
            (
                "02",
                "Validate and route",
                "FastAPI + Pydantic",
                "Schemas, API-key roles, public request limits",
            ),
            (
                "03",
                "Retrieve and rank",
                "PostgreSQL + pgvector",
                "Full-text + hashed vectors; RRF, rerank, compress",
            ),
            (
                "04",
                "Compose the assessment",
                "Structured model boundary",
                "Hypotheses and timeline reference returned evidence IDs",
            ),
            (
                "05",
                "Review proposed tools",
                "Read-only gateway",
                "Separate approval, scope checks, budgets, and audit",
            ),
        ]
        for i, (number, title, tech, description) in enumerate(rows):
            top = 166 + i * 71
            self.rect(MARGIN, top, CONTENT, 61, PALE)
            self.label(number, MARGIN + 13, top + 14)
            self.text(title, MARGIN + 46, top + 8, 239, 11.5, bold=True)
            self.text(tech, MARGIN + 297, top + 9, 198, 9, MUTED)
            self.text(description, MARGIN + 46, top + 33, 447, 9.5, MUTED)
            if i < len(rows) - 1:
                self.rect(MARGIN + 21, top + 61, 1, 10, BLUE)

        self.label("WHAT RUNS IN THE HOSTED DEMO", MARGIN, 546)
        self.text(
            "One Render web service; PostgreSQL/pgvector; deterministic generation; "
            "simulator telemetry; inline jobs. Visitors can investigate without a key. "
            "Operational routes retain API-key checks.",
            MARGIN,
            568,
            CONTENT,
            10.5,
        )
        self.label("WHAT THE REPOSITORY ALSO SUPPORTS", MARGIN, 633)
        self.text(
            "A configurable Responses-compatible model with repair, fallback, cache, "
            "and cost tracking; fixed production telemetry adapters; Redis Queue workers; "
            "Docker Compose and Kubernetes deployment resources.",
            MARGIN,
            655,
            CONTENT,
            10.5,
        )
        self.rect(MARGIN, 722, CONTENT, 54, "E8F4F1")
        self.text(
            "<b>Design tradeoff:</b> the public experience stays credential-free and "
            "reproducible. External models and real telemetry require a separately "
            "configured deployment and environment-specific validation.",
            MARGIN + 12,
            732,
            CONTENT - 24,
            10,
            TEAL,
        )
        self.pdf.showPage()

    def verification(self) -> None:
        self.new_page(
            4,
            "03 / VERIFICATION",
            "Show the work. Bound the claims.",
            "Recorded v2.2.0 verification, September 7, 2026. Source links are clickable.",
        )
        table_top = 167
        self.rect(MARGIN, table_top, CONTENT, 30, INK)
        self.text("CHECK", MARGIN + 12, table_top + 7, 230, 9, WHITE, True)
        self.text("RECORDED RESULT", 303, table_top + 7, 237, 9, WHITE, True)
        checks = [
            ("Local backend suite", "40 passed; 1 Docker-dependent test skipped"),
            ("Backend coverage", "82.21% across measured packages"),
            ("Synthetic evaluation", "100 cases; strict and A/B gates passed"),
            ("Desktop + mobile browser checks", "4 Playwright checks passed"),
            ("GitHub CI + release images", "All four CI jobs; three image builds passed"),
        ]
        for i, (name, result) in enumerate(checks):
            top = table_top + 30 + i * 37
            self.rect(MARGIN, top, CONTENT, 37, PALE if i % 2 == 0 else "F9FBFE")
            self.text(name, MARGIN + 12, top + 10, 237, 9.5, bold=True)
            self.text(result, 303, top + 10, 237, 9.3)
        self.label("HOW TO INTERPRET THE RESULTS", MARGIN, 407)
        self.text(
            "The benchmark uses an in-memory index and deterministic generation with "
            "80 development and 20 held-out synthetic cases. Its proxy checks cover "
            "root-cause term matching, source hits, evidence-ID validity, and expected tools. "
            "They demonstrate regression behavior, not production accuracy or semantic proof.",
            MARGIN,
            429,
            CONTENT,
            10.5,
        )
        self.label("LIMITATIONS THAT SHAPE THE NEXT ITERATION", MARGIN, 510)
        self.text(
            "Feature-hashed vectors are not trained semantic embeddings. Hypothesis "
            "confidence is heuristic. The shared demo corpus must stay synthetic; the "
            "application is not a tenant-isolation system. Free hosting can sleep, and the "
            "database has an expiry. Real-team use needs historical-incident evaluation "
            "and deployment-specific data access, retention, and backup decisions.",
            MARGIN,
            532,
            CONTENT,
            10.5,
        )
        self.label("ENGINEERING VALUE", MARGIN, 632)
        self.text(
            "A working full-stack project that connects retrieval, evidence provenance, "
            "human-controlled tools, runtime configuration, and automated delivery into "
            "one inspectable incident workflow.",
            MARGIN,
            654,
            CONTENT,
            11.5,
            bold=True,
        )
        links = [("Source", REPO), ("CI evidence", CI), ("Release images", IMAGES)]
        x = MARGIN
        for label, url in links:
            self.link_button(label, url, x, 737, 158)
            x += 170
        self.pdf.showPage()

    def build(self) -> None:
        self.cover()
        self.product()
        self.architecture()
        self.verification()
        self.pdf.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    Portfolio(args.output).build()
    print(f"Created {escape(str(args.output.resolve()))}")


if __name__ == "__main__":
    main()
