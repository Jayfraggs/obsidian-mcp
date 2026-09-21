"""GraphService – generate chart and graph code blocks for Obsidian notes.

Supports two Obsidian graph plugins:

DataCharts (https://github.com/jcf-402/datacharts)
---------------------------------------------------
Renders interactive line / bar / scatter / pie / radar charts via Chart.js
and Mathjs inside a ``datachart`` fenced code block.  No server-side
rendering — this service writes the raw code block; Obsidian's DataCharts
plugin processes it at display time.

Block syntax (all fields optional unless noted):
    ```datachart
    title :: My Chart
    type  :: line          # line | bar | scatter | pie | doughnut | radar
    # ── equation-based datasets ───────────────────────────────────────
    y1 :: x^2
    y1.label :: Parabola
    range :: -10,10        # global x range (start,end)
    steps :: 200           # number of sample points
    # ── manual datasets ──────────────────────────────────────────────
    data.label :: Manual
    data.x :: 1,2,3,4,5
    data.y :: 2,4,1,3,5
    # ── source from markdown table ───────────────────────────────────
    source :: path/to/note.md
    source.table :: 0      # 0-indexed table number in that note
    source.x :: Column A   # header name for x
    source.y :: Column B   # header name for y
    ```

Mathematica Plot (https://github.com/marcosnicolau/obsidian-mathematica-plot)
------------------------------------------------------------------------------
Renders 2-D and 3-D Wolfram Mathematica plots via wolframscript.
Requires the user to have wolframscript installed.

Block syntax (pair of YAML-like comment lines the plugin reads):
    ```mathematica-plot
    Plot[Sin[x], {x, -Pi, Pi}]
    ```
or for 3-D:
    ```mathematica-plot
    Plot3D[Sin[x] Cos[y], {x, -Pi, Pi}, {y, -Pi, Pi}]
    ```

This service generates complete, ready-to-paste markdown that can be written
directly to a vault note with VaultService.
"""

from __future__ import annotations

import textwrap
from typing import Any

from obsidian_mcp.vault.service import VaultService


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _kv(key: str, value: Any) -> str:
    """Return 'key :: value' line, skipping None values."""
    if value is None:
        return ""
    return f"{key} :: {value}"


def _block(lang: str, body: str) -> str:
    """Wrap body in a fenced code block."""
    return f"```{lang}\n{body.strip()}\n```"


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class GraphService:
    """Generate DataCharts and Mathematica Plot code blocks for vault notes."""

    def __init__(self, vault: VaultService) -> None:
        self._vault = vault

    # ── DataCharts ────────────────────────────────────────────────────────

    def datachart_equation(
        self,
        path: str,
        heading: str,
        equations: list[dict[str, str]],
        chart_type: str = "line",
        x_range: tuple[float, float] = (-10, 10),
        steps: int = 200,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Write a DataCharts equation-based chart to a vault note.

        Creates (or appends to) *path* with a ``datachart`` block that plots
        one or more mathematical equations using Mathjs.

        Args:
            path: Vault-relative destination note path (e.g. ``Graphs/trig.md``).
            heading: Markdown heading to insert before the block.
            equations: List of dicts, each with at least ``expr`` (the Mathjs
                expression, e.g. ``"sin(x)"``).  Optional keys: ``label``,
                ``color``.
            chart_type: DataCharts chart type — ``line``, ``bar``, or
                ``scatter``.
            x_range: (start, end) for the x-axis sample range.
            steps: Number of sample points along the x range.
            title: Optional chart title string.

        Returns:
            ``{path, block, status}`` dict.
        """
        lines: list[str] = []
        if title:
            lines.append(_kv("title", title))
        lines.append(_kv("type", chart_type))
        lines.append(_kv("range", f"{x_range[0]},{x_range[1]}"))
        lines.append(_kv("steps", steps))
        for i, eq in enumerate(equations, start=1):
            name = f"y{i}"
            lines.append(_kv(name, eq["expr"]))
            if eq.get("label"):
                lines.append(_kv(f"{name}.label", eq["label"]))
            if eq.get("color"):
                lines.append(_kv(f"{name}.color", eq["color"]))

        body = "\n".join(ln for ln in lines if ln)
        block = _block("datachart", body)
        content = f"\n## {heading}\n\n{block}\n"
        self._vault.append_note(path, content)
        return {"path": path, "block": block, "status": "written"}

    def datachart_manual(
        self,
        path: str,
        heading: str,
        datasets: list[dict[str, Any]],
        chart_type: str = "line",
        title: str | None = None,
    ) -> dict[str, Any]:
        """Write a DataCharts chart with manually specified data points.

        Args:
            path: Vault-relative destination note path.
            heading: Markdown heading to insert before the block.
            datasets: List of dicts, each with:
                - ``label`` (str): Dataset legend label.
                - ``x`` (list[float | str]): X values.
                - ``y`` (list[float]): Y values.
                Optional keys: ``color``.
            chart_type: DataCharts chart type — ``line``, ``bar``, ``scatter``,
                ``pie``, ``doughnut``, ``radar``.
            title: Optional chart title string.

        Returns:
            ``{path, block, status}`` dict.
        """
        lines: list[str] = []
        if title:
            lines.append(_kv("title", title))
        lines.append(_kv("type", chart_type))
        for ds in datasets:
            prefix = f"data.{ds['label']}" if len(datasets) > 1 else "data"
            lines.append(_kv(f"{prefix}.label", ds["label"]))
            lines.append(_kv(f"{prefix}.x", ",".join(str(v) for v in ds["x"])))
            lines.append(_kv(f"{prefix}.y", ",".join(str(v) for v in ds["y"])))
            if ds.get("color"):
                lines.append(_kv(f"{prefix}.color", ds["color"]))

        body = "\n".join(ln for ln in lines if ln)
        block = _block("datachart", body)
        content = f"\n## {heading}\n\n{block}\n"
        self._vault.append_note(path, content)
        return {"path": path, "block": block, "status": "written"}

    def datachart_from_table(
        self,
        path: str,
        heading: str,
        source_note: str,
        x_column: str,
        y_column: str,
        table_index: int = 0,
        chart_type: str = "line",
        title: str | None = None,
    ) -> dict[str, Any]:
        """Write a DataCharts chart sourced from a Markdown table in another note.

        Args:
            path: Vault-relative destination note path.
            heading: Markdown heading to insert before the block.
            source_note: Vault-relative path to the note containing the table.
            x_column: Header name of the column to use as x values.
            y_column: Header name of the column to use as y values.
            table_index: Zero-based index of the table in the source note.
            chart_type: DataCharts chart type.
            title: Optional chart title string.

        Returns:
            ``{path, block, status}`` dict.
        """
        lines: list[str] = []
        if title:
            lines.append(_kv("title", title))
        lines.append(_kv("type", chart_type))
        lines.append(_kv("source", source_note))
        lines.append(_kv("source.table", table_index))
        lines.append(_kv("source.x", x_column))
        lines.append(_kv("source.y", y_column))

        body = "\n".join(ln for ln in lines if ln)
        block = _block("datachart", body)
        content = f"\n## {heading}\n\n{block}\n"
        self._vault.append_note(path, content)
        return {"path": path, "block": block, "status": "written"}

    # ── Mathematica Plot ──────────────────────────────────────────────────

    def mathematica_plot_2d(
        self,
        path: str,
        heading: str,
        expression: str,
        variable: str = "x",
        x_range: tuple[float | str, float | str] = ("-Pi", "Pi"),
        plot_options: str | None = None,
    ) -> dict[str, Any]:
        """Write a 2-D Mathematica Plot block to a vault note.

        Generates a ``mathematica-plot`` fenced block using the Wolfram
        ``Plot[...]`` function.  Requires wolframscript installed on the user's
        machine.

        Args:
            path: Vault-relative destination note path.
            heading: Markdown heading to insert before the block.
            expression: Wolfram expression to plot (e.g. ``"Sin[x]"``).
            variable: The free variable (default ``"x"``).
            x_range: (start, end) for the variable range. Wolfram constants
                like ``"Pi"`` are valid.
            plot_options: Optional extra Wolfram plot options appended inside
                ``Plot[]`` (e.g. ``"PlotStyle -> Red"``).

        Returns:
            ``{path, block, status}`` dict.
        """
        range_str = f"{x_range[0]},{x_range[1]}"
        opts = f", {plot_options}" if plot_options else ""
        wl = f"Plot[{expression}, {{{variable}, {range_str}}}{opts}]"
        block = _block("mathematica-plot", wl)
        content = f"\n## {heading}\n\n{block}\n"
        self._vault.append_note(path, content)
        return {"path": path, "block": block, "status": "written"}

    def mathematica_plot_3d(
        self,
        path: str,
        heading: str,
        expression: str,
        variable_x: str = "x",
        variable_y: str = "y",
        x_range: tuple[float | str, float | str] = ("-Pi", "Pi"),
        y_range: tuple[float | str, float | str] = ("-Pi", "Pi"),
        plot_options: str | None = None,
    ) -> dict[str, Any]:
        """Write a 3-D Mathematica Plot3D block to a vault note.

        Generates a ``mathematica-plot`` fenced block using the Wolfram
        ``Plot3D[...]`` function.

        Args:
            path: Vault-relative destination note path.
            heading: Markdown heading to insert before the block.
            expression: Wolfram expression to plot (e.g. ``"Sin[x]*Cos[y]"``).
            variable_x: First free variable (default ``"x"``).
            variable_y: Second free variable (default ``"y"``).
            x_range: Range for variable_x.
            y_range: Range for variable_y.
            plot_options: Optional extra Wolfram plot options.

        Returns:
            ``{path, block, status}`` dict.
        """
        xr = f"{x_range[0]},{x_range[1]}"
        yr = f"{y_range[0]},{y_range[1]}"
        opts = f", {plot_options}" if plot_options else ""
        wl = f"Plot3D[{expression}, {{{variable_x}, {xr}}}, {{{variable_y}, {yr}}}{opts}]"
        block = _block("mathematica-plot", wl)
        content = f"\n## {heading}\n\n{block}\n"
        self._vault.append_note(path, content)
        return {"path": path, "block": block, "status": "written"}

    def mathematica_custom(
        self,
        path: str,
        heading: str,
        wolfram_code: str,
    ) -> dict[str, Any]:
        """Write an arbitrary Wolfram Mathematica block to a vault note.

        Use this for any Mathematica visualisation command that doesn't fit
        the Plot / Plot3D helpers (e.g. ``ParametricPlot``,
        ``ListLinePlot``, ``DensityPlot``).

        Args:
            path: Vault-relative destination note path.
            heading: Markdown heading to insert before the block.
            wolfram_code: Full Wolfram Mathematica expression string.

        Returns:
            ``{path, block, status}`` dict.
        """
        block = _block("mathematica-plot", wolfram_code)
        content = f"\n## {heading}\n\n{block}\n"
        self._vault.append_note(path, content)
        return {"path": path, "block": block, "status": "written"}

    # ── Block-only helpers (no write) ─────────────────────────────────────

    def datachart_block(
        self,
        chart_type: str,
        equations: list[dict[str, str]] | None = None,
        datasets: list[dict[str, Any]] | None = None,
        x_range: tuple[float, float] = (-10, 10),
        steps: int = 200,
        title: str | None = None,
    ) -> str:
        """Return a raw DataCharts code block string without writing to the vault.

        Useful when you want the block to be embedded inside a larger note
        rather than appended standalone.

        Args:
            chart_type: DataCharts chart type.
            equations: Equation dicts (``expr``, optional ``label``, ``color``).
            datasets: Manual dataset dicts (``label``, ``x``, ``y``, optional ``color``).
            x_range: Sample range for equation-based charts.
            steps: Number of sample points.
            title: Optional chart title.

        Returns:
            Fenced ``datachart`` block string.
        """
        lines: list[str] = []
        if title:
            lines.append(_kv("title", title))
        lines.append(_kv("type", chart_type))
        if equations:
            lines.append(_kv("range", f"{x_range[0]},{x_range[1]}"))
            lines.append(_kv("steps", steps))
            for i, eq in enumerate(equations, start=1):
                name = f"y{i}"
                lines.append(_kv(name, eq["expr"]))
                if eq.get("label"):
                    lines.append(_kv(f"{name}.label", eq["label"]))
                if eq.get("color"):
                    lines.append(_kv(f"{name}.color", eq["color"]))
        if datasets:
            for ds in datasets:
                prefix = f"data.{ds['label']}" if datasets else "data"
                lines.append(_kv(f"{prefix}.label", ds["label"]))
                lines.append(_kv(f"{prefix}.x", ",".join(str(v) for v in ds["x"])))
                lines.append(_kv(f"{prefix}.y", ",".join(str(v) for v in ds["y"])))
                if ds.get("color"):
                    lines.append(_kv(f"{prefix}.color", ds["color"]))
        body = "\n".join(ln for ln in lines if ln)
        return _block("datachart", body)

    def mathematica_block(self, wolfram_code: str) -> str:
        """Return a raw Mathematica Plot code block string without writing to the vault.

        Args:
            wolfram_code: Full Wolfram Mathematica expression string.

        Returns:
            Fenced ``mathematica-plot`` block string.
        """
        return _block("mathematica-plot", wolfram_code)
