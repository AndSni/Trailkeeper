"""Project report PDF for the web console (BLUEPRINT sec 11). Pure-Python
via fpdf2 - no system libraries, unlike WeasyPrint. Picks up a system
Unicode TTF (Liberation / DejaVu / Noto) so Latvian text renders; falls
back to a core Latin-1 font with lossy transliteration if none is found.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.models import Membership
from app.web.dashboard import gather

_FONT_CANDIDATES = [
    ("/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",
     "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
     "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
     "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
]

INK = (30, 42, 36)
MUTED = (92, 107, 98)
LINE = (210, 208, 201)


def _resolve_font() -> tuple[str, str] | None:
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).is_file() and Path(bold).is_file():
            return regular, bold
    return None


class _Report(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4", unit="mm")
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 18, 18)
        font = _resolve_font()
        if font is not None:
            self.add_font("Body", "", font[0])
            self.add_font("Body", "B", font[1])
            self._family = "Body"
            self._unicode = True
        else:
            self._family = "Helvetica"
            self._unicode = False

    def _t(self, text: str) -> str:
        if self._unicode:
            return text
        return text.encode("latin-1", "replace").decode("latin-1")

    def font(self, *, bold: bool = False, size: float = 10) -> None:
        self.set_font(self._family, "B" if bold else "", size)

    def h1(self, text: str) -> None:
        self.set_text_color(*INK)
        self.font(bold=True, size=18)
        self.multi_cell(0, 9, self._t(text))
        self.ln(1)

    def h2(self, text: str) -> None:
        self.ln(3)
        self.set_text_color(*INK)
        self.font(bold=True, size=12)
        self.multi_cell(0, 7, self._t(text))
        self.ln(1)

    def muted_line(self, text: str) -> None:
        self.set_text_color(*MUTED)
        self.font(size=9)
        self.multi_cell(0, 5, self._t(text))

    def table(self, headers: list[str], rows: list[list[object]], widths: list[float]) -> None:
        avail = self.w - self.l_margin - self.r_margin
        widths = [w / sum(widths) * avail for w in widths]
        self.set_draw_color(*LINE)

        self.set_text_color(*MUTED)
        self.font(bold=True, size=8)
        for head, wdt in zip(headers, widths, strict=True):
            self.cell(wdt, 7, self._t(head.upper()), border="B")
        self.ln(7)

        self.set_text_color(*INK)
        self.font(size=9)
        if not rows:
            self.cell(avail, 7, self._t("(none)"), border="B")
            self.ln(7)
            return
        for row in rows:
            for value, wdt in zip(row, widths, strict=True):
                self.cell(wdt, 7, self._t("" if value is None else str(value)), border="B")
            self.ln(7)


def report_pdf(db: Session, membership: Membership, project_id: str | None) -> bytes:
    ctx = gather(db, membership, project_id)
    pdf = _Report()
    pdf.add_page()

    pdf.h1(ctx["org_name"] or "Trailkeeper")
    sel = ctx["selected"]
    pdf.muted_line(
        f"Project report · {sel['name'] if sel else 'no project selected'} · "
        f"generated {dt.date.today().isoformat()}"
    )

    pdf.h2("Overview")
    pdf.table(
        ["Metric", "Value"],
        [
            ["Members", ctx["member_count"]],
            ["Projects", len(ctx["projects"])],
            ["Structures", sum(ctx["structure_status"].values())],
        ],
        [3, 1],
    )

    pdf.h2("Projects")
    pdf.table(
        ["Name", "Status", "Open", "Done", "Members"],
        [[p["name"], p["status"], p["open"], p["done"], p["members"]] for p in ctx["projects"]],
        [4, 2, 1, 1, 1.4],
    )

    if sel is not None:
        pdf.h2(f"{sel['name']} — tasks by status")
        pdf.table(
            ["Status", "Count"],
            [[s.replace("_", " "), n] for s, n in ctx["task_status"].items()],
            [3, 1],
        )

        pdf.h2("Hours per member")
        pdf.table(
            ["Member", "Logged", "Segments", "Total"],
            [
                [r["name"], r["logged_hours"], r["segment_hours"], r["total_hours"]]
                for r in ctx["hours_per_member"]
            ],
            [3, 1, 1.4, 1],
        )

        pdf.h2("Job-type productivity")
        pdf.table(
            ["Job type", "Qty", "Person-h", "Rate", "Target", "Δ"],
            [
                [
                    r["label"], f"{r['quantity']} {r['unit']}", r["person_hours"],
                    "–" if r["mean_rate"] is None else r["mean_rate"],
                    "–" if r["expected_rate"] is None else r["expected_rate"],
                    "–" if r["delta"] is None else r["delta"],
                ]
                for r in ctx["job_productivity"]
            ],
            [3, 1.6, 1.4, 1, 1, 1],
        )

    pdf.h2("Structures by status")
    pdf.table(
        ["Status", "Count"],
        [[s.replace("_", " "), n] for s, n in ctx["structure_status"].items()],
        [3, 1],
    )

    pdf.h2("Recent inspections")
    pdf.table(
        ["Date", "Structure", "Inspector", "Risk", "Condition set"],
        [
            [i["on"], i["structure"], i["inspector"], i["risk"] or "–",
             (i["condition"] or "–").replace("_", " ")]
            for i in ctx["recent_inspections"]
        ],
        [1.4, 2.4, 2, 1.2, 1.6],
    )

    return bytes(pdf.output())
