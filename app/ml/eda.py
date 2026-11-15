"""Exploratory data analysis: summary numbers and charts for the cleaned incidents.

Every figure comes straight from the data file. When the data is synthetic, every
chart title and the summary say so.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files only; no window needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.ml.zones import CATEGORIES

PURPLE = "#6d28d9"
NAVY = "#0f1b3d"
PINK = "#f9a8d4"
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def load_clean(path):
    return pd.read_csv(path, parse_dates=["incident_time"])


def _suffix(df):
    return " (synthetic demo data)" if bool(df["is_synthetic"].all()) else ""


def build_summary(df):
    """Plain numbers about the data. Raises ValueError if the table is empty."""
    if df.empty:
        raise ValueError("There are no rows to analyse.")

    weekday_counts = df["day_of_week"].value_counts().reindex(range(7), fill_value=0)
    hour_counts = df["hour"].value_counts().reindex(range(24), fill_value=0)
    return {
        "rows": int(len(df)),
        "date_from": str(df["incident_time"].min().date()),
        "date_to": str(df["incident_time"].max().date()),
        "all_synthetic": bool(df["is_synthetic"].all()),
        "category_counts": {c: int((df["category"] == c).sum()) for c in CATEGORIES},
        "severity_counts": {int(k): int(v) for k, v in
                            df["severity"].value_counts().reindex(range(1, 6), fill_value=0).items()},
        "severity_mean": round(float(df["severity"].mean()), 2),
        "zone_counts": {k: int(v) for k, v in df["zone"].value_counts().items()},
        "zone_mean_severity": {k: round(float(v), 2) for k, v in
                               df.groupby("zone")["severity"].mean().sort_values(ascending=False).items()},
        "peak_hour": int(hour_counts.idxmax()),
        "night_share_pct": round(float(df["is_night"].mean() * 100), 1),
        "weekend_share_pct": round(float(df["is_weekend"].mean() * 100), 1),
        "busiest_weekday": DAY_NAMES[int(weekday_counts.idxmax())],
    }


def _finish(fig, ax, path, title, xlabel=None, ylabel=None):
    ax.set_title(title, fontsize=12, color=NAVY, loc="left", fontweight="bold")
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def make_charts(df, out_dir):
    """Save the charts as PNG files and return their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = _suffix(df)
    paths = []

    # 1. Incidents per category
    counts = df["category"].value_counts().reindex(CATEGORIES, fill_value=0).sort_values()
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.barh(counts.index, counts.values, color=PURPLE)
    for y, v in enumerate(counts.values):
        ax.text(v, y, f" {v}", va="center", fontsize=9)
    paths.append(_finish(fig, ax, out_dir / "category_counts.png",
                         f"Incidents by category{tag}", xlabel="Number of incidents"))

    # 2. Incidents per hour of day (night hours highlighted)
    hours = df["hour"].value_counts().reindex(range(24), fill_value=0)
    colours = [NAVY if (h >= 21 or h < 5) else PURPLE for h in range(24)]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.bar(range(24), hours.values, color=colours)
    ax.set_xticks(range(0, 24, 2))
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=NAVY), plt.Rectangle((0, 0), 1, 1, color=PURPLE)],
              labels=["Night (21:00 to 04:59)", "Other hours"], frameon=False, fontsize=8)
    paths.append(_finish(fig, ax, out_dir / "incidents_by_hour.png",
                         f"Incidents by hour of day{tag}", xlabel="Hour (local time)", ylabel="Incidents"))

    # 3. Incidents per weekday
    weekdays = df["day_of_week"].value_counts().reindex(range(7), fill_value=0)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar([d[:3] for d in DAY_NAMES], weekdays.values, color=PURPLE)
    paths.append(_finish(fig, ax, out_dir / "incidents_by_weekday.png",
                         f"Incidents by day of week{tag}", ylabel="Incidents"))

    # 4. Severity distribution
    severity = df["severity"].value_counts().reindex(range(1, 6), fill_value=0)
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.bar([str(s) for s in severity.index], severity.values, color=PINK, edgecolor=PURPLE)
    paths.append(_finish(fig, ax, out_dir / "severity_distribution.png",
                         f"Severity of incidents{tag}", xlabel="Severity (1 minor to 5 severe)", ylabel="Incidents"))

    # 5. Zone summary: how many, and how severe on average
    zone = df.groupby("zone").agg(count=("severity", "size"), mean_severity=("severity", "mean"))
    zone = zone.sort_values("count")
    short = [z.replace("Demo ", "") for z in zone.index]
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    left.barh(short, zone["count"], color=PURPLE)
    left.set_title("Incidents", fontsize=10, color=NAVY, loc="left")
    right.barh(short, zone["mean_severity"], color=PINK, edgecolor=PURPLE)
    right.set_title("Average severity (1 to 5)", fontsize=10, color=NAVY, loc="left")
    right.set_xlim(0, 5)
    for side in ("top", "right"):
        left.spines[side].set_visible(False)
        right.spines[side].set_visible(False)
    fig.suptitle(f"Incidents and severity by zone{tag}", x=0.01, ha="left", fontsize=12,
                 color=NAVY, fontweight="bold")
    fig.tight_layout()
    path = out_dir / "zone_summary.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths.append(path)

    # 6. Category by hour heatmap
    grid = (df.groupby(["category", "hour"]).size().unstack(fill_value=0)
              .reindex(index=list(CATEGORIES), columns=range(24), fill_value=0))
    fig, ax = plt.subplots(figsize=(9, 3.4))
    image = ax.imshow(grid.values, aspect="auto", cmap="Purples")
    ax.set_yticks(range(len(CATEGORIES)), CATEGORIES)
    ax.set_xticks(range(0, 24, 2))
    fig.colorbar(image, ax=ax, label="Incidents")
    paths.append(_finish(fig, ax, out_dir / "category_by_hour_heatmap.png",
                         f"When each type of incident happens{tag}", xlabel="Hour (local time)"))

    # 7. Where incidents happen (plain scatter, no map tiles)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    points = ax.scatter(df["longitude"], df["latitude"], c=df["severity"], cmap="Purples",
                        vmin=1, vmax=5, s=12, alpha=0.7, edgecolors="none")
    fig.colorbar(points, ax=ax, label="Severity")
    ax.set_aspect(1 / np.cos(np.radians(df["latitude"].mean())))
    paths.append(_finish(fig, ax, out_dir / "location_scatter.png",
                         f"Where incidents were reported{tag}", xlabel="Longitude", ylabel="Latitude"))

    return paths


def write_summary_markdown(summary, chart_paths, path):
    """Write eda_summary.md with a clear synthetic-data warning and the numbers."""
    lines = ["# SafeRadar AI - exploratory data analysis", ""]
    if summary["all_synthetic"]:
        lines += [
            "> **SYNTHETIC DATA.** Every row was generated by the developer for testing. "
            "The patterns below were written into the generator, so they show assumptions, "
            "not real events. They say nothing about how safe any real place is.",
            "",
        ]
    lines += [
        f"- Rows analysed: **{summary['rows']}**",
        f"- Period covered: {summary['date_from']} to {summary['date_to']}",
        f"- Average severity: {summary['severity_mean']} / 5",
        f"- Busiest hour: {summary['peak_hour']:02d}:00",
        f"- Busiest weekday: {summary['busiest_weekday']}",
        f"- Share of incidents at night (21:00 to 04:59): {summary['night_share_pct']}%",
        f"- Share on weekends: {summary['weekend_share_pct']}%",
        "",
        "## Incidents by category",
        "",
    ]
    lines += [f"- {name}: {count}" for name, count in summary["category_counts"].items()]
    lines += ["", "## Incidents by zone (with average severity)", ""]
    lines += [f"- {name}: {count} incidents, average severity {summary['zone_mean_severity'][name]}"
              for name, count in summary["zone_counts"].items()]
    lines += ["", "## Charts", ""]
    lines += [f"![{Path(p).stem}]({Path(p).name})" for p in chart_paths]
    lines += [""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return Path(path)