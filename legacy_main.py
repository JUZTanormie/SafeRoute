import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
except ImportError:
    pass

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
import base64
import threading
import webbrowser

from database import (
    create_database, get_profile, save_profile, save_journey, get_saved_journeys,
    count_reports_by_author,
)
from community_service import community_service
from models import Route
from safety_engine import SafetyAnalyzer
from report_ai import ReportIntelligence
from risk_model import SafetyRiskModel
from map_service import (
    MAP_PROVIDER,
    autocomplete_location_candidates,
    fetch_google_static_map,
    get_place_details,
    get_route,
    get_route_recommendations,
    google_maps_directions_url,
    new_session_token,
    search_location_candidates,
    geocode_location,
)
from journey_briefing import JourneyBriefingEngine
from route_intelligence import RouteIntelligence


# ============================================================
# BACKEND INITIALIZATION
# ============================================================

create_database()


def get_reports(include_demo=False, include_inactive=False):
    """Use the shared community API when configured; otherwise use local SQLite."""
    return community_service.get_reports(
        include_demo=include_demo,
        include_inactive=include_inactive,
    )


def get_report_author():
    """Apply the profile's report-name privacy preference."""
    profile = get_profile()
    preferences = profile.get("preferences", {})
    if preferences.get("share_display_name", True):
        return profile.get("display_name", "Community member")
    return "Anonymous contributor"


def add_report(location, category, severity, description, timestamp=None, latitude=None, longitude=None):
    """Compatibility wrapper used by the existing route-based report form."""
    return community_service.submit_report(
        location=location,
        category=category,
        severity=severity,
        description=description,
        latitude=latitude,
        longitude=longitude,
        author=get_report_author(),
    )

report_ai = ReportIntelligence()
risk_model = SafetyRiskModel()
journey_briefing = JourneyBriefingEngine()
route_intelligence = RouteIntelligence()

current_route = None
selected_locations = {"from": None, "to": None}
current_analysis = None
current_route_data = None
hotspot_marker = None
map_photo_ref = None
route_recommendations = {}
location_autocomplete_after = {"from": None, "to": None}
location_last_query = {"from": "", "to": ""}
google_location_sessions = {"from": new_session_token(), "to": new_session_token()}


# ============================================================
# THEME
# ============================================================

BG = "#0b1220"
SIDEBAR = "#0f172a"
CARD = "#111c31"
CARD_2 = "#16243d"
TEXT = "#e7eefc"
MUTED = "#93a4c3"
ACCENT = "#22d3ee"
ACCENT_2 = "#38bdf8"
DANGER = "#fb7185"
WARNING = "#fbbf24"
SUCCESS = "#34d399"
BORDER = "#243555"

FONT = "Segoe UI"


# ============================================================
# ROOT
# ============================================================

root = tk.Tk()
root.title("SafeRoute")
root.geometry("1280x820")
root.minsize(1050, 720)
root.configure(bg=BG)


style = ttk.Style(root)
try:
    style.theme_use("clam")
except tk.TclError:
    pass

style.configure(
    "Safe.TCombobox",
    fieldbackground=CARD,
    background=CARD,
    foreground=TEXT,
    arrowcolor=ACCENT,
    bordercolor=BORDER,
)


# ============================================================
# HELPERS
# ============================================================


def clear_frame(frame):
    for widget in frame.winfo_children():
        widget.destroy()


def set_status(message, level="info"):
    status_colors = {
        "info": MUTED,
        "success": SUCCESS,
        "warning": WARNING,
        "error": DANGER,
    }
    status_label.config(
        text=message,
        fg=status_colors.get(level, MUTED),
    )


def card(parent, padx=18, pady=18):
    frame = tk.Frame(
        parent,
        bg=CARD,
        highlightthickness=1,
        highlightbackground=BORDER,
        bd=0,
    )
    return frame


def section_title(parent, title, subtitle=None):
    tk.Label(
        parent,
        text=title,
        bg=parent.cget("bg"),
        fg=TEXT,
        font=(FONT, 15, "bold"),
    ).pack(anchor="w")

    if subtitle:
        tk.Label(
            parent,
            text=subtitle,
            bg=parent.cget("bg"),
            fg=MUTED,
            font=(FONT, 9),
            wraplength=760,
        ).pack(anchor="w", pady=(3, 10))


def make_button(parent, text, command, primary=False, width=None):
    kwargs = {
        "text": text,
        "command": command,
        "font": (FONT, 10, "bold" if primary else "normal"),
        "relief": "flat",
        "bd": 0,
        "cursor": "hand2",
        "padx": 14,
        "pady": 9,
    }

    if primary:
        kwargs.update({
            "bg": ACCENT,
            "fg": BG,
            "activebackground": ACCENT_2,
            "activeforeground": BG,
        })
    else:
        kwargs.update({
            "bg": CARD_2,
            "fg": TEXT,
            "activebackground": BORDER,
            "activeforeground": TEXT,
        })

    if width is not None:
        kwargs["width"] = width

    return tk.Button(parent, **kwargs)


def value_label(parent, value, size=18, color=TEXT):
    return tk.Label(
        parent,
        text=value,
        bg=parent.cget("bg"),
        fg=color,
        font=(FONT, size, "bold"),
    )


def make_entry(parent, text=""):
    entry = tk.Entry(
        parent,
        bg=CARD_2,
        fg=TEXT,
        insertbackground=TEXT,
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
        font=(FONT, 10),
    )
    if text:
        entry.insert(0, text)
    return entry


def create_scrollable(parent):
    canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    content = tk.Frame(canvas, bg=BG)

    content.bind(
        "<Configure>",
        lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
    )

    window_id = canvas.create_window((0, 0), window=content, anchor="nw")

    def resize_content(event):
        canvas.itemconfigure(window_id, width=event.width)

    canvas.bind("<Configure>", resize_content)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    return content


def calculate_hour_24():
    hour_value = int(hour_box.get())
    return (
        0 if hour_value == 12 else hour_value
        if period_box.get() == "AM"
        else 12 if hour_value == 12 else hour_value + 12
    )


def journey_time_text():
    return f"{hour_box.get()}:{minute_box.get()} {period_box.get()}"


def get_journey_type(hour_24):
    if hour_24 < 5:
        return "Midnight"
    if hour_24 < 8:
        return "Early Morning"
    if hour_24 < 12:
        return "Morning"
    if hour_24 < 16:
        return "Afternoon"
    if hour_24 < 21:
        return "Evening"
    return "Night"


def update_journey_type(event=None):
    hour_24 = calculate_hour_24()
    journey_type = get_journey_type(hour_24)
    journey_type_value.config(text=journey_type)


# ============================================================
# APP LAYOUT
# ============================================================

sidebar = tk.Frame(root, bg=SIDEBAR, width=220)
sidebar.pack(side="left", fill="y")
sidebar.pack_propagate(False)

main = tk.Frame(root, bg=BG)
main.pack(side="left", fill="both", expand=True)

header = tk.Frame(main, bg=BG, height=70)
header.pack(fill="x")
header.pack_propagate(False)

content_host = tk.Frame(main, bg=BG)
content_host.pack(fill="both", expand=True, padx=18, pady=(0, 12))

status_bar = tk.Frame(main, bg=SIDEBAR, height=28)
status_bar.pack(fill="x", side="bottom")
status_bar.pack_propagate(False)

status_label = tk.Label(
    status_bar,
    text="Ready.",
    bg=SIDEBAR,
    fg=MUTED,
    font=(FONT, 9),
    anchor="w",
)
status_label.pack(fill="both", padx=12)


# ============================================================
# SIDEBAR
# ============================================================

tk.Label(
    sidebar,
    text="SafeRoute",
    bg=SIDEBAR,
    fg=ACCENT,
    font=(FONT, 24, "bold"),
).pack(anchor="w", padx=24, pady=(25, 2))

tk.Label(
    sidebar,
    text="COMMUNITY JOURNEY SAFETY",
    bg=SIDEBAR,
    fg=MUTED,
    font=(FONT, 8, "bold"),
).pack(anchor="w", padx=25, pady=(0, 30))

nav_frame = tk.Frame(sidebar, bg=SIDEBAR)
nav_frame.pack(fill="x")

nav_buttons = {}
page_frames = {}


def set_nav_active(name):
    for button_name, button in nav_buttons.items():
        if button_name == name:
            button.config(bg=ACCENT, fg=BG)
        else:
            button.config(bg=SIDEBAR, fg=TEXT)


def show_page(name):
    frame = page_frames[name]
    frame.tkraise()
    set_nav_active(name)
    if name == "results":
        render_results_page()
    elif name == "advanced":
        render_advanced_page()
    elif name == "report":
        render_report_page()
    elif name == "communities":
        render_communities_page()
    elif name == "profile":
        render_profile_page()


def add_nav(name, label):
    button = tk.Button(
        nav_frame,
        text=label,
        command=lambda: show_page(name),
        bg=SIDEBAR,
        fg=TEXT,
        activebackground=ACCENT,
        activeforeground=BG,
        relief="flat",
        bd=0,
        anchor="w",
        font=(FONT, 10, "bold"),
        padx=24,
        pady=12,
        cursor="hand2",
    )
    button.pack(fill="x", pady=2)
    nav_buttons[name] = button


add_nav("journey", "⌂   Plan Journey")
add_nav("results", "◈   Safety Results")
add_nav("report", "＋   Report Issue")
add_nav("advanced", "≡   Advanced View")
add_nav("communities", "◎   Communities")
add_nav("profile", "◉   Profile")


tk.Label(
    sidebar,
    text="",
    bg=SIDEBAR,
).pack(expand=True)

tk.Label(
    sidebar,
    text="Core engine + AI + ML",
    bg=SIDEBAR,
    fg=MUTED,
    font=(FONT, 8),
).pack(anchor="w", padx=25, pady=(0, 25))


# ============================================================
# HEADER
# ============================================================

header_title = tk.Label(
    header,
    text="Plan a Journey",
    bg=BG,
    fg=TEXT,
    font=(FONT, 20, "bold"),
)
header_title.pack(side="left", padx=5, pady=18)

header_meta = tk.Label(
    header,
    text="",
    bg=BG,
    fg=MUTED,
    font=(FONT, 9),
)
header_meta.pack(side="right", padx=8, pady=18)


# ============================================================
# JOURNEY PAGE
# ============================================================

journey_page = tk.Frame(content_host, bg=BG)
journey_page.grid(row=0, column=0, sticky="nsew")
page_frames["journey"] = journey_page

journey_page.grid_rowconfigure(1, weight=1)
journey_page.grid_columnconfigure(0, weight=3)
journey_page.grid_columnconfigure(1, weight=4)

left_panel = tk.Frame(journey_page, bg=BG)
left_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))

right_panel = tk.Frame(journey_page, bg=BG)
right_panel.grid(row=0, column=1, rowspan=2, sticky="nsew")


# Location card
location_card = card(left_panel)
location_card.configure(width=470, height=315)
location_card.pack_propagate(False)
location_card.pack(fill="x", pady=(0, 10))

section_title(
    location_card,
    "Journey setup",
    "Search and select the exact start and destination before routing.",
)


tk.Label(
    location_card,
    text="Starting location",
    bg=CARD,
    fg=MUTED,
    font=(FONT, 9, "bold"),
).pack(anchor="w", padx=18, pady=(3, 3))

from_row = tk.Frame(location_card, bg=CARD)
from_row.pack(fill="x", padx=18)
from_entry = make_entry(from_row, "SRMIST TIRUCHIRAPPALLI")
from_entry.pack(side="left", fill="x", expand=True, ipady=6)
make_button(
    from_row,
    "Search",
    lambda: choose_location("from"),
).pack(side="left", padx=(7, 0))

from_result_row = tk.Frame(location_card, bg=CARD)
from_result_row.pack(fill="x", padx=18, pady=(5, 7))

from_candidates = tk.Listbox(
    from_result_row,
    bg=CARD_2,
    fg=TEXT,
    selectbackground=ACCENT,
    selectforeground=BG,
    relief="flat",
    height=2,
    font=(FONT, 8),
)
from_candidates.pack(side="left", fill="both", expand=True)

make_button(
    from_result_row,
    "Use Selected",
    lambda: apply_location_selection("from"),
    primary=True,
    width=14,
).pack(side="left", padx=(7, 0), fill="y")


tk.Label(
    location_card,
    text="Destination",
    bg=CARD,
    fg=MUTED,
    font=(FONT, 9, "bold"),
).pack(anchor="w", padx=18, pady=(1, 3))

to_row = tk.Frame(location_card, bg=CARD)
to_row.pack(fill="x", padx=18)
to_entry = make_entry(to_row, "THANJAVUR NEW BUS STAND")
to_entry.pack(side="left", fill="x", expand=True, ipady=6)
make_button(
    to_row,
    "Search",
    lambda: choose_location("to"),
).pack(side="left", padx=(7, 0))

to_result_row = tk.Frame(location_card, bg=CARD)
to_result_row.pack(fill="x", padx=18, pady=(5, 4))

to_candidates = tk.Listbox(
    to_result_row,
    bg=CARD_2,
    fg=TEXT,
    selectbackground=ACCENT,
    selectforeground=BG,
    relief="flat",
    height=2,
    font=(FONT, 8),
)
to_candidates.pack(side="left", fill="both", expand=True)

make_button(
    to_result_row,
    "Use Selected",
    lambda: apply_location_selection("to"),
    primary=True,
    width=14,
).pack(side="left", padx=(7, 0), fill="y")

help_label = tk.Label(
    location_card,
    text=(
        ("Google suggestions appear while you type. Double-click to select."
         if MAP_PROVIDER == "google"
         else "OpenStreetMap search runs when you press Search; no keystroke autocomplete." )
    ),
    bg=CARD,
    fg=MUTED,
    font=(FONT, 8),
)
help_label.pack(anchor="w", padx=18, pady=(1, 0))


def _clear_location_suggestions(kind):
    listbox = from_candidates if kind == "from" else to_candidates
    listbox.delete(0, tk.END)
    listbox.candidates = []


def _show_location_predictions(kind, candidates):
    listbox = from_candidates if kind == "from" else to_candidates
    entry = from_entry if kind == "from" else to_entry
    query = entry.get().strip()

    listbox.delete(0, tk.END)
    listbox.candidates = candidates

    for candidate in candidates:
        text = candidate.get("display_name", "Location")
        secondary = candidate.get("secondary_text", "")
        if secondary and secondary not in text:
            text = f"{text}  •  {secondary}"
        listbox.insert(tk.END, text)

    if candidates and entry.get().strip() == query:
        listbox.selection_set(0)
        set_status(
            f"Google found {len(candidates)} location suggestions.",
            "success",
        )


def _fetch_google_predictions(kind, query, session_token):
    try:
        candidates = autocomplete_location_candidates(
            query,
            session_token=session_token,
            location_bias=(10.7905, 78.7047, 50000.0),
            limit=6,
        )

        def finish():
            entry = from_entry if kind == "from" else to_entry
            if entry.get().strip() != query:
                return
            _show_location_predictions(kind, candidates)

        root.after(0, finish)
    except Exception as error:
        message = f"Google suggestions failed: {error}"
        root.after(0, lambda: set_status(message, "error"))


def schedule_google_predictions(kind):
    entry = from_entry if kind == "from" else to_entry
    query = entry.get().strip()

    previous = location_autocomplete_after.get(kind)
    if previous is not None:
        try:
            root.after_cancel(previous)
        except Exception:
            pass
        location_autocomplete_after[kind] = None

    _clear_location_suggestions(kind)

    if MAP_PROVIDER != "google" or len(query) < 2:
        return

    token = google_location_sessions[kind]
    location_autocomplete_after[kind] = root.after(300, lambda: threading.Thread(
        target=_fetch_google_predictions,
        args=(kind, query, token),
        daemon=True,
    ).start())


def location_changed(kind):
    selected_locations[kind] = None
    entry = from_entry if kind == "from" else to_entry
    query = entry.get().strip()

    if MAP_PROVIDER == "google":
        # A new non-empty query after an empty field starts a fresh Places session.
        if query and not location_last_query[kind]:
            google_location_sessions[kind] = new_session_token()
        location_last_query[kind] = query
        schedule_google_predictions(kind)


from_entry.bind("<KeyRelease>", lambda event: location_changed("from"))
to_entry.bind("<KeyRelease>", lambda event: location_changed("to"))


# Time card
settings_card = card(left_panel)
settings_card.configure(width=470, height=240)
settings_card.pack_propagate(False)
settings_card.pack(fill="x", pady=(0, 10))

section_title(
    settings_card,
    "Journey context",
    "The selected time affects time-sensitive safety analysis.",
)

time_grid = tk.Frame(settings_card, bg=CARD)
time_grid.pack(fill="x", padx=18, pady=4)

hour_box = ttk.Combobox(
    time_grid,
    values=[f"{h:02}" for h in range(1, 13)],
    width=5,
    state="readonly",
    style="Safe.TCombobox",
)
hour_box.set("08")
hour_box.grid(row=0, column=0, padx=(0, 4))

tk.Label(time_grid, text=":", bg=CARD, fg=TEXT, font=(FONT, 11)).grid(row=0, column=1)

minute_box = ttk.Combobox(
    time_grid,
    values=[f"{m:02}" for m in range(0, 60, 5)],
    width=5,
    state="readonly",
    style="Safe.TCombobox",
)
minute_box.set("00")
minute_box.grid(row=0, column=2, padx=4)

period_box = ttk.Combobox(
    time_grid,
    values=["AM", "PM"],
    width=5,
    state="readonly",
    style="Safe.TCombobox",
)
period_box.set("PM")
period_box.grid(row=0, column=3, padx=4)

journey_type_value = tk.Label(
    settings_card,
    text="Evening",
    bg=CARD,
    fg=ACCENT,
    font=(FONT, 15, "bold"),
)
journey_type_value.pack(anchor="w", padx=18, pady=(10, 12))

hour_box.bind("<<ComboboxSelected>>", update_journey_type)
period_box.bind("<<ComboboxSelected>>", update_journey_type)
update_journey_type()

button_row = tk.Frame(settings_card, bg=CARD)
button_row.pack(fill="x", padx=18, pady=(2, 4))

# The real command is attached after calculate_route() is defined.
calculate_route_button = make_button(
    button_row,
    "Calculate Route",
    lambda: None,
    primary=True,
)
calculate_route_button.pack(side="left", fill="x", expand=True)

make_button(
    button_row,
    "Analyze Journey",
    lambda: analyze_journey(),
).pack(side="left", fill="x", expand=True, padx=(8, 0))


# Route card
route_card = card(right_panel)
route_card.pack(fill="both", expand=True)

route_header = tk.Frame(route_card, bg=CARD)
route_header.pack(fill="x", padx=18, pady=(16, 8))

tk.Label(
    route_header,
    text="Route",
    bg=CARD,
    fg=TEXT,
    font=(FONT, 15, "bold"),
).pack(side="left")

route_summary_label = tk.Label(
    route_header,
    text="No route calculated",
    bg=CARD,
    fg=MUTED,
    font=(FONT, 9),
)
route_summary_label.pack(side="right")

make_button(
    route_header,
    "Open route in Google Maps",
    lambda: open_current_route_in_google(),
).pack(side="right", padx=(8, 0))

# Selected hotspot detail panel. It stays inside the main window so
# hotspot inspection never opens another application window.
hotspot_detail_frame = tk.Frame(
    route_card,
    bg=CARD,
    highlightthickness=1,
    highlightbackground=BORDER,
    height=120,
)
hotspot_detail_frame.pack(fill="x", padx=18, pady=(0, 10))
hotspot_detail_frame.pack_propagate(False)

# Nearby-service assistance is available when the optional Google provider is
# enabled. Keep it out of the OSM-first layout when it is not applicable.
route_recommendation_frame = tk.Frame(
    route_card,
    bg=CARD,
    highlightthickness=1,
    highlightbackground=BORDER,
    height=118,
)
route_recommendation_frame.pack_propagate(False)
route_recommendation_frame.pack(fill="x", padx=18, pady=(0, 10))

map_container = tk.Frame(
    route_card,
    bg=CARD_2,
    height=375,
)
map_container.pack_propagate(False)
map_container.pack(fill="x", padx=18, pady=(0, 14))

map_photo_label = tk.Label(
    map_container,
    bg=CARD_2,
    fg=MUTED,
    font=(FONT, 10),
    text=(
        "Interactive OpenStreetMap route will appear here."
        if MAP_PROVIDER == "osm"
        else "Google route map will appear here."
    ),
)
map_photo_label.pack(fill="both", expand=True)

map_widget = None
hotspot_marker = None


def clear_route_recommendations():
    for widget in route_recommendation_frame.winfo_children():
        widget.destroy()

    tk.Label(
        route_recommendation_frame,
        text="Nearby essential services",
        bg=CARD,
        fg=TEXT,
        font=(FONT, 8, "bold"),
    ).pack(anchor="w", padx=12, pady=(8, 1))

    tk.Label(
        route_recommendation_frame,
        text="Hospitals, police stations and pharmacies near this route will appear here.",
        bg=CARD,
        fg=MUTED,
        font=(FONT, 8),
    ).pack(anchor="w", padx=12, pady=(0, 8))


def render_route_recommendations(data):
    clear_route_recommendations()
    total = sum(len(items) for items in data.values())

    tk.Label(
        route_recommendation_frame,
        text="Nearby essential services",
        bg=CARD,
        fg=TEXT,
        font=(FONT, 8, "bold"),
    ).pack(anchor="w", padx=12, pady=(7, 1))

    if total == 0:
        tk.Label(
            route_recommendation_frame,
            text="No nearby hospitals, police stations or pharmacies were returned for this route.",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))
        return

    count_text = " • ".join(
        f"{name}: {len(items)}"
        for name, items in data.items()
        if items
    )

    tk.Label(
        route_recommendation_frame,
        text=count_text,
        bg=CARD,
        fg=ACCENT,
        font=(FONT, 8, "bold"),
    ).pack(anchor="e", padx=12, pady=(0, 3))

    chips = tk.Frame(route_recommendation_frame, bg=CARD)
    chips.pack(fill="x", padx=10, pady=(0, 7))

    shown = 0
    for category, items in data.items():
        if not items:
            continue

        place = items[0]
        chip = tk.Frame(
            chips,
            bg=CARD_2,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        chip.pack(side="left", fill="x", expand=True, padx=2)

        tk.Label(
            chip,
            text=category,
            bg=CARD_2,
            fg=ACCENT,
            font=(FONT, 8, "bold"),
        ).pack(anchor="w", padx=8, pady=(5, 0))

        name = place.get("display_name", "Nearby place")
        if len(name) > 34:
            name = name[:31] + "..."

        tk.Label(
            chip,
            text=name,
            bg=CARD_2,
            fg=MUTED,
            font=(FONT, 8),
        ).pack(anchor="w", padx=8, pady=(1, 5))

        shown += 1
        if shown >= 3:
            break


def _google_photo_image(image_bytes):
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return tk.PhotoImage(data=encoded)


def render_google_route_map(route_data, center=None, zoom=None):
    global map_photo_ref

    for widget in map_container.winfo_children():
        widget.destroy()

    loading = tk.Label(
        map_container,
        text="Loading Google Maps…",
        bg=CARD_2,
        fg=MUTED,
        font=(FONT, 10),
    )
    loading.pack(expand=True)

    def worker():
        try:
            image_bytes = fetch_google_static_map(
                route_data,
                width=620,
                height=350,
                center=center,
                zoom=zoom,
            )

            def apply():
                global map_photo_ref
                if not loading.winfo_exists():
                    return
                photo = _google_photo_image(image_bytes)
                for widget in map_container.winfo_children():
                    widget.destroy()
                label = tk.Label(map_container, bg=CARD_2, image=photo)
                label.pack(fill="both", expand=True)
                map_photo_ref = photo

            root.after(0, apply)
        except Exception as error:
            message = str(error)
            root.after(
                0,
                lambda: (
                    loading.config(
                        text=f"Google map could not be loaded.\n{message}",
                        fg=DANGER,
                    )
                ),
            )

    threading.Thread(target=worker, daemon=True).start()


def render_route_map(route_data, center=None, zoom=None):
    if MAP_PROVIDER == "google":
        render_google_route_map(route_data, center=center, zoom=zoom)
        return

    # Primary interactive OpenStreetMap route view.
    global map_widget
    for widget in map_container.winfo_children():
        widget.destroy()

    try:
        from tkintermapview import TkinterMapView
    except ImportError:
        tk.Label(
            map_container,
            text="Interactive OSM map dependency missing. Run: pip install -r requirements.txt",
            bg=CARD_2,
            fg=DANGER,
            font=(FONT, 10),
        ).pack(expand=True)
        map_widget = None
        return

    map_widget = TkinterMapView(map_container, width=700, height=500, corner_radius=0)
    map_widget.pack(fill="both", expand=True)
    map_widget.set_path(route_data["route_points"])
    start = route_data["start"]
    destination = route_data["destination"]
    map_widget.set_marker(start["latitude"], start["longitude"], text="Start")
    map_widget.set_marker(destination["latitude"], destination["longitude"], text="Destination")
    route_points = route_data["route_points"]
    min_lat = min(p[0] for p in route_points)
    max_lat = max(p[0] for p in route_points)
    min_lon = min(p[1] for p in route_points)
    max_lon = max(p[1] for p in route_points)
    map_widget.set_position((min_lat + max_lat) / 2, (min_lon + max_lon) / 2)
    map_widget.set_zoom(11)


clear_route_recommendations()
if MAP_PROVIDER != "google":
    route_recommendation_frame.pack_forget()

# ============================================================
# INTERACTIVE ROUTE HOTSPOTS
# ============================================================


def open_current_route_in_google():
    if current_route is None:
        set_status("Calculate a route first.", "warning")
        return

    start = selected_locations.get("from")
    destination = selected_locations.get("to")
    if not start or not destination:
        set_status("Select both route locations first.", "warning")
        return

    webbrowser.open(google_maps_directions_url(start, destination))
    set_status("Opened the journey in Google Maps.", "success")


def get_hotspot_midpoint(hotspot):
    """Return the route midpoint for a named hotspot segment."""

    if current_route is None:
        return None

    segment_name = hotspot.get("segment")

    for segment in current_route.segments:
        if segment.get("name") == segment_name:
            midpoint = segment.get("midpoint")
            if midpoint:
                return midpoint

    return None


def clear_hotspot_detail():
    for widget in hotspot_detail_frame.winfo_children():
        widget.destroy()

    tk.Label(
        hotspot_detail_frame,
        text="Route hotspot focus",
        bg=CARD,
        fg=MUTED,
        font=(FONT, 8, "bold"),
    ).pack(anchor="w", padx=14, pady=(10, 2))

    tk.Label(
        hotspot_detail_frame,
        text='Select "View on Map" from a hotspot to inspect its location and evidence.',
        bg=CARD,
        fg=MUTED,
        font=(FONT, 8),
        wraplength=850,
        justify="left",
    ).pack(anchor="w", padx=14, pady=(0, 10))


def show_hotspot_detail(hotspot):
    clear_hotspot_detail()

    segment_name = hotspot.get("segment", "Unknown segment")
    categories = ", ".join(hotspot.get("categories", [])[:3])

    title_row = tk.Frame(hotspot_detail_frame, bg=CARD)
    title_row.pack(fill="x", padx=14, pady=(10, 2))

    tk.Label(
        title_row,
        text=f"Focused: {segment_name}",
        bg=CARD,
        fg=ACCENT,
        font=(FONT, 10, "bold"),
    ).pack(side="left")

    tk.Label(
        title_row,
        text=f"{hotspot.get('contribution_share', 0):.1f}% concern contribution",
        bg=CARD,
        fg=TEXT,
        font=(FONT, 8, "bold"),
    ).pack(side="right")

    context_text = (
        f"{hotspot.get('report_count', 0)} report(s)"
        + (f" • {categories}" if categories else "")
        + (
            f" • avg {hotspot['average_distance_km'] * 1000:.0f} m from route"
            if hotspot.get("average_distance_km") is not None
            else ""
        )
    )

    tk.Label(
        hotspot_detail_frame,
        text=context_text,
        bg=CARD,
        fg=MUTED,
        font=(FONT, 8),
        justify="left",
    ).pack(anchor="w", padx=14, pady=(0, 4))

    reports = []
    if current_analysis:
        reports = [
            report
            for report in current_analysis.get("relevant_reports", [])
            if (report.matched_segment or report.location or "Unknown segment") == segment_name
        ]

    if reports:
        for report in reports[:2]:
            distance = getattr(report, "matched_distance_km", None)
            distance_text = (
                f" • {distance * 1000:.0f} m from route"
                if distance is not None
                else ""
            )

            evidence_text = (
                f"• {report.category} • severity {report.severity}/3{distance_text}\n"
                f"  {report.description}"
            )

            tk.Label(
                hotspot_detail_frame,
                text=evidence_text,
                bg=CARD,
                fg=TEXT,
                font=(FONT, 8),
                justify="left",
                wraplength=950,
            ).pack(anchor="w", padx=14, pady=1)
    else:
        tk.Label(
            hotspot_detail_frame,
            text="No individual report evidence could be matched to this segment.",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8),
        ).pack(anchor="w", padx=14, pady=2)


def focus_hotspot(hotspot):
    midpoint = get_hotspot_midpoint(hotspot)

    if midpoint is None:
        set_status(
            f"Map focus is unavailable for {hotspot.get('segment', 'this hotspot')}.",
            "warning",
        )
        return

    show_hotspot_detail(hotspot)
    show_page("journey")

    if current_route_data is None:
        set_status("Route map data is unavailable.", "warning")
        return

    if MAP_PROVIDER == "google":
        render_route_map(
            current_route_data,
            center=midpoint,
            zoom=15,
        )
        set_status(
            f"Google map focused on {hotspot.get('segment', 'selected hotspot')}.",
            "success",
        )
    else:
        def apply_focus():
            if map_widget is None:
                set_status("Route map is not available.", "warning")
                return
            map_widget.set_position(midpoint[0], midpoint[1])
            map_widget.set_zoom(14)
            set_status(
                f"Map focused on {hotspot.get('segment', 'selected hotspot')}.",
                "success",
            )
        root.after(120, apply_focus)

# Initialize the detail panel before the first route is calculated.
clear_hotspot_detail()


# ============================================================
# LOCATION SEARCH
# ============================================================


def choose_location(kind, on_selected=None):
    entry = from_entry if kind == "from" else to_entry
    listbox = from_candidates if kind == "from" else to_candidates
    query = entry.get().strip()

    if not query:
        set_status("Enter a location before searching.", "warning")
        return

    root.config(cursor="watch")
    set_status(
        f"Searching {MAP_PROVIDER.upper()} for the starting location..."
        if kind == "from"
        else f"Searching {MAP_PROVIDER.upper()} for the destination...",
        "info",
    )
    root.update()

    def worker():
        try:
            candidates = search_location_candidates(
                query,
                context="Tamil Nadu, India",
                limit=6,
            )

            def apply_results():
                listbox.delete(0, tk.END)
                listbox.candidates = candidates
                listbox.pending_callback = on_selected

                for candidate in candidates:
                    label = candidate.get("display_name", "Location")
                    address = candidate.get("formatted_address", "")
                    if address and address != label:
                        label = f"{label}  •  {address}"
                    listbox.insert(tk.END, label)

                if candidates:
                    listbox.selection_set(0)
                    listbox.focus_set()
                    set_status(
                        f"{MAP_PROVIDER.upper()} found {len(candidates)} locations. Select the exact place.",
                        "success",
                    )
                else:
                    set_status(
                        f"{MAP_PROVIDER.upper()} returned no matching locations. Try a landmark, road, or bus stand.",
                        "warning",
                    )
                root.config(cursor="")

            root.after(0, apply_results)
        except Exception as error:
            root.after(
                0,
                lambda: (
                    set_status(f"Google location search failed: {error}", "error"),
                    root.config(cursor=""),
                ),
            )

    threading.Thread(target=worker, daemon=True).start()


def apply_location_selection(kind, continue_callback=None):
    entry = from_entry if kind == "from" else to_entry
    listbox = from_candidates if kind == "from" else to_candidates
    candidates = getattr(listbox, "candidates", [])
    selection = listbox.curselection()

    if not candidates or not selection:
        set_status("Select a location suggestion first.", "warning")
        return

    initial_candidate = candidates[selection[0]]
    root.config(cursor="watch")

    def worker():
        try:
            selected_candidate = dict(initial_candidate)

            if MAP_PROVIDER == "google" and (
                selected_candidate.get("latitude") is None
                or selected_candidate.get("longitude") is None
            ):
                place_id = selected_candidate.get("place_id")
                if not place_id:
                    raise RuntimeError("Google result has no Place ID.")

                selected_candidate = get_place_details(
                    place_id,
                    session_token=google_location_sessions[kind],
                )

            callback = continue_callback
            if callback is None:
                callback = getattr(listbox, "pending_callback", None)

            def apply(selected=selected_candidate, next_callback=callback):
                selected_locations[kind] = selected
                entry.delete(0, tk.END)
                entry.insert(
                    0,
                    selected.get("display_name", "Selected location"),
                )
                listbox.pending_callback = None
                google_location_sessions[kind] = new_session_token()
                set_status(
                    f"Selected {selected.get('display_name', 'location')} ({MAP_PROVIDER.upper()}).",
                    "success",
                )
                root.config(cursor="")

                if next_callback is not None:
                    root.after(100, next_callback)

            root.after(0, apply)

        except Exception as error:
            message = str(error)
            root.after(
                0,
                lambda message=message: (
                    set_status(
                        f"Google place selection failed: {message}",
                        "error",
                    ),
                    root.config(cursor=""),
                ),
            )

    threading.Thread(target=worker, daemon=True).start()


def apply_pending_location_selection(kind):
    apply_location_selection(kind)


def bind_location_double_click(kind):
    listbox = from_candidates if kind == "from" else to_candidates
    listbox.bind(
        "<Double-Button-1>",
        lambda event: apply_pending_location_selection(kind),
    )


bind_location_double_click("from")
bind_location_double_click("to")


# ============================================================
# ROUTE CALCULATION
# ============================================================


def selected_departure_datetime():
    now = datetime.now().astimezone()
    target = now.replace(
        hour=int(hour_box.get()) % 12 + (12 if period_box.get() == "PM" and int(hour_box.get()) != 12 else 0),
        minute=int(minute_box.get()),
        second=0,
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    return target


def calculate_route():
    global current_route, current_route_data, route_recommendations

    start_location = from_entry.get().strip()
    destination = to_entry.get().strip()

    if not start_location or not destination:
        set_status("Enter both a starting location and destination.", "warning")
        return

    if selected_locations["from"] is None:
        choose_location("from", on_selected=calculate_route)
        return

    if selected_locations["to"] is None:
        choose_location("to", on_selected=calculate_route)
        return

    root.config(cursor="watch")
    set_status(
        "Calculating Google traffic-aware route..."
        if MAP_PROVIDER == "google"
        else "Calculating OpenStreetMap / OSRM route (traffic data is not included)...",
        "info",
    )
    root.update()

    def worker():
        try:
            departure = selected_departure_datetime()
            route_data = get_route(
                selected_locations["from"],
                selected_locations["to"],
                departure_datetime=departure,
            )

            def apply_route():
                global current_route, current_route_data, route_recommendations

                current_route_data = route_data
                current_route = Route(
                    "Google Live Route" if MAP_PROVIDER == "google" else "OpenStreetMap Route",
                    route_data["distance_km"],
                    route_data["duration_min"],
                    route_data["segments"],
                    route_data["route_points"],
                    (
                        route_data["start"]["latitude"],
                        route_data["start"]["longitude"],
                    ),
                    (
                        route_data["destination"]["latitude"],
                        route_data["destination"]["longitude"],
                    ),
                )

                route_summary_label.config(
                    text=(
                        f"{current_route.distance} km  •  "
                        f"{current_route.estimated_time} min"
                        + ("  •  Google traffic-aware" if MAP_PROVIDER == "google" else "  •  OSM / OSRM · no live traffic")
                    )
                )

                render_route_map(route_data)
                header_meta.config(
                    text=(
                        f"{selected_locations['from']['display_name']} → "
                        f"{selected_locations['to']['display_name']}"
                    )
                )
                clear_route_recommendations()

                if MAP_PROVIDER == "google":
                    def recommendation_worker():
                        global route_recommendations
                        try:
                            results = get_route_recommendations(route_data)
                        except Exception:
                            results = {"Hospital": [], "Police station": [], "Pharmacy": []}
                        route_recommendations = results
                        root.after(0, lambda: render_route_recommendations(results))

                    threading.Thread(target=recommendation_worker, daemon=True).start()

                set_status(
                    "Google route calculated. Checking route-side assistance..."
                    if MAP_PROVIDER == "google"
                    else "OpenStreetMap route calculated. Live traffic data is not included.",
                    "success",
                )
                root.config(cursor="")

            root.after(0, apply_route)

        except Exception as error:
            message = str(error)
            root.after(
                0,
                lambda message=message: (
                    set_status(f"Route calculation failed: {message}", "error"),
                    root.config(cursor=""),
                ),
            )

    threading.Thread(target=worker, daemon=True).start()


# Attach the real command now that calculate_route() exists.
calculate_route_button.config(command=calculate_route)


# ============================================================
# ANALYSIS
# ============================================================


def analyze_journey():
    global current_analysis

    if current_route is None:
        set_status("Calculate a route before analyzing the journey.", "warning")
        return

    hour_24 = calculate_hour_24()
    journey_type = get_journey_type(hour_24)
    journey_time = journey_time_text()

    root.config(cursor="watch")
    set_status("Analyzing route safety...", "info")
    root.update()

    try:
        reports = get_reports()

        analyzer = SafetyAnalyzer(
            reports,
            journey_type=journey_type,
            journey_hour=hour_24,
        )

        relevant_reports = analyzer.find_relevant_reports(
            current_route
        )

        raw_score = analyzer.calculate_score(
            relevant_reports
        )

        # Keep the user-facing safety concern scale strictly within 0-10.
        score = max(
            0.0,
            min(
                10.0,
                float(raw_score)
            )
        )
        score = round(score, 2)

        assessment = analyzer.get_assessment(score)
        confidence = analyzer.get_confidence(relevant_reports)

        ml_explanation = risk_model.explain_route_risk(
            relevant_reports,
            hour_24,
        )

        briefing = analyzer.generate_briefing(
            relevant_reports,
            score,
        )

        contextual_briefing = journey_briefing.generate(
            relevant_reports=relevant_reports,
            score=score,
            assessment=assessment,
            confidence=confidence,
            ml_risk=ml_explanation["risk"],
            ml_factors=ml_explanation["factors"],
            journey_time=journey_time,
            journey_type=journey_type,
            route_distance=current_route.distance,
            route_duration=current_route.estimated_time,
        )

        hotspot_analysis = route_intelligence.analyze(
            relevant_reports,
            analyzer,
            max_segments=3,
        )

        current_analysis = {
            "hour_24": hour_24,
            "journey_type": journey_type,
            "journey_time": journey_time,
            "relevant_reports": relevant_reports,
            "score": score,
            "assessment": assessment,
            "confidence": confidence,
            "ml_risk": ml_explanation["risk"],
            "ml_factors": ml_explanation["factors"],
            "briefing": briefing,
            "contextual_briefing": contextual_briefing,
            "hotspots": hotspot_analysis,
        }

        show_page("results")
        set_status("Journey analysis completed.", "success")

    except Exception as error:
        set_status(f"Analysis failed: {error}", "error")
    finally:
        root.config(cursor="")


# ============================================================
# RESULTS PAGE
# ============================================================

results_page = tk.Frame(content_host, bg=BG)
results_page.grid(row=0, column=0, sticky="nsew")
page_frames["results"] = results_page


def render_results_page():
    clear_frame(results_page)

    if not current_analysis:
        tk.Label(
            results_page,
            text="No journey analysis yet.",
            bg=BG,
            fg=MUTED,
            font=(FONT, 14),
        ).pack(expand=True)
        return

    data = current_analysis
    score = max(0.0, min(10.0, float(data["score"])))
    score = round(score, 2)

    if score == 0:
        score_color = MUTED
        concern_label = "Insufficient Safety Data"
    elif score <= 3:
        score_color = SUCCESS
        concern_label = "Low Concern"
    elif score <= 7:
        score_color = WARNING
        concern_label = "Moderate Concern"
    else:
        score_color = DANGER
        concern_label = "High Concern"

    scroll_content = create_scrollable(results_page)

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    top = tk.Frame(scroll_content, bg=BG)
    top.pack(fill="x", pady=(0, 12))

    tk.Label(
        top,
        text="Journey Safety",
        bg=BG,
        fg=TEXT,
        font=(FONT, 21, "bold"),
    ).pack(anchor="w")

    tk.Label(
        top,
        text=(
            f"{selected_locations['from']['display_name']}  →  "
            f"{selected_locations['to']['display_name']}"
        ),
        bg=BG,
        fg=MUTED,
        font=(FONT, 9),
        wraplength=1000,
    ).pack(anchor="w", pady=(3, 0))

    # --------------------------------------------------------
    # PRIMARY SAFETY RESULT
    # --------------------------------------------------------

    score_card = card(scroll_content)
    score_card.pack(fill="x", pady=(0, 12))

    score_inner = tk.Frame(score_card, bg=CARD)
    score_inner.pack(fill="x", padx=20, pady=18)

    score_left = tk.Frame(score_inner, bg=CARD)
    score_left.pack(side="left", fill="x", expand=True)

    tk.Label(
        score_left,
        text="SAFETY CONCERN",
        bg=CARD,
        fg=MUTED,
        font=(FONT, 9, "bold"),
    ).pack(anchor="w")

    tk.Label(
        score_left,
        text=(
            "10/10"
            if score >= 10
            else f"{score:.2f}/10"
        ),
        bg=CARD,
        fg=score_color,
        font=(FONT, 34, "bold"),
    ).pack(anchor="w", pady=(2, 0))

    tk.Label(
        score_left,
        text=concern_label,
        bg=CARD,
        fg=TEXT,
        font=(FONT, 12, "bold"),
    ).pack(anchor="w", pady=(0, 3))

    tk.Label(
        score_left,
        text="Higher score = greater safety concern. 10/10 is the maximum concern level.",
        bg=CARD,
        fg=MUTED,
        font=(FONT, 8),
        wraplength=700,
    ).pack(anchor="w")

    score_right = tk.Frame(score_inner, bg=CARD)
    score_right.pack(side="right", padx=(25, 0))

    tk.Label(
        score_right,
        text="DATA CONFIDENCE",
        bg=CARD,
        fg=MUTED,
        font=(FONT, 8, "bold"),
    ).pack(anchor="e")

    tk.Label(
        score_right,
        text=data["confidence"],
        bg=CARD,
        fg=TEXT,
        font=(FONT, 15, "bold"),
    ).pack(anchor="e", pady=(2, 5))

    tk.Label(
        score_right,
        text=(
            f"{len(data['relevant_reports'])} relevant report(s)"
        ),
        bg=CARD,
        fg=MUTED,
        font=(FONT, 8),
    ).pack(anchor="e")

    # --------------------------------------------------------
    # WHAT THIS MEANS
    # --------------------------------------------------------

    meaning_card = card(scroll_content)
    meaning_card.pack(fill="x", pady=(0, 12))

    section_title(
        meaning_card,
        "What this means",
        "A simple interpretation of the available journey evidence.",
    )

    tk.Label(
        meaning_card,
        text=data["contextual_briefing"]["headline"],
        bg=CARD,
        fg=TEXT,
        font=(FONT, 13, "bold"),
        wraplength=1000,
        justify="left",
    ).pack(anchor="w", padx=18, pady=(0, 4))

    tk.Label(
        meaning_card,
        text=data["contextual_briefing"]["summary"],
        bg=CARD,
        fg=TEXT,
        font=(FONT, 9),
        wraplength=1000,
        justify="left",
    ).pack(anchor="w", padx=18, pady=(0, 8))

    tk.Label(
        meaning_card,
        text=data["contextual_briefing"]["recommendation"],
        bg=CARD,
        fg=MUTED,
        font=(FONT, 9, "italic"),
        wraplength=1000,
        justify="left",
    ).pack(anchor="w", padx=18, pady=(0, 16))

    # --------------------------------------------------------
    # JOURNEY CONTEXT
    # --------------------------------------------------------

    context_card = card(scroll_content)
    context_card.pack(fill="x", pady=(0, 12))

    section_title(
        context_card,
        "Journey context",
        "The selected journey time is part of the safety analysis.",
    )

    context_row = tk.Frame(context_card, bg=CARD)
    context_row.pack(fill="x", padx=18, pady=(0, 16))

    context_items = [
        ("Time", data["journey_time"]),
        ("Period", data["journey_type"]),
        ("Distance", f"{current_route.distance} km"),
        ("Est. duration", f"{current_route.estimated_time} min"),
    ]

    for index, (label, value) in enumerate(context_items):
        cell = tk.Frame(context_row, bg=CARD)
        cell.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0 if index == 0 else 8, 8 if index < 3 else 0),
        )

        tk.Label(
            cell,
            text=label.upper(),
            bg=CARD,
            fg=MUTED,
            font=(FONT, 7, "bold"),
        ).pack(anchor="w")

        tk.Label(
            cell,
            text=value,
            bg=CARD,
            fg=TEXT,
            font=(FONT, 10, "bold"),
        ).pack(anchor="w", pady=(2, 0))

    # --------------------------------------------------------
    # CONCERN DRIVERS
    # --------------------------------------------------------

    drivers_card = card(scroll_content)
    drivers_card.pack(fill="x", pady=(0, 12))

    reports = data["relevant_reports"]
    category_counts = {}

    for report in reports:
        category_counts[report.category] = (
            category_counts.get(report.category, 0)
            + 1
        )

    ranked_categories = sorted(
        category_counts.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    section_title(
        drivers_card,
        "Main concern drivers",
        "Categories represented by the community observations used in this analysis.",
    )

    if not ranked_categories:
        tk.Label(
            drivers_card,
            text="No community concern categories were found for this route.",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w", padx=18, pady=(0, 16))
    else:
        for category, count in ranked_categories[:4]:
            row = tk.Frame(drivers_card, bg=CARD_2)
            row.pack(fill="x", padx=18, pady=3)

            tk.Label(
                row,
                text=category,
                bg=CARD_2,
                fg=TEXT,
                font=(FONT, 9, "bold"),
            ).pack(side="left", padx=12, pady=8)

            tk.Label(
                row,
                text=f"{count} report(s)",
                bg=CARD_2,
                fg=MUTED,
                font=(FONT, 8),
            ).pack(side="right", padx=12, pady=8)

        tk.Label(
            drivers_card,
            text="The category mix is descriptive evidence, not a guarantee of actual danger.",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8, "italic"),
        ).pack(anchor="w", padx=18, pady=(8, 14))

    # --------------------------------------------------------
    # ROUTE HOTSPOTS
    # --------------------------------------------------------

    hotspot_card = card(scroll_content)
    hotspot_card.pack(fill="x", pady=(0, 12))

    section_title(
        hotspot_card,
        "Route hotspots",
        data["hotspots"]["summary"]
        + "  Click View on Map to focus the route and inspect the evidence.",
    )

    hotspots = data["hotspots"]["hotspots"]

    if not hotspots:
        tk.Label(
            hotspot_card,
            text="No route hotspot data is available.",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w", padx=18, pady=(0, 16))
    else:
        for index, hotspot in enumerate(hotspots, start=1):
            row = tk.Frame(
                hotspot_card,
                bg=CARD_2,
                highlightthickness=1,
                highlightbackground=BORDER,
            )
            row.pack(fill="x", padx=18, pady=4)

            title_row = tk.Frame(row, bg=CARD_2)
            title_row.pack(fill="x", padx=12, pady=(7, 2))

            tk.Label(
                title_row,
                text=f"{index}. {hotspot['segment']}",
                bg=CARD_2,
                fg=TEXT,
                font=(FONT, 10, "bold"),
            ).pack(side="left")

            make_button(
                title_row,
                "View on Map",
                lambda h=hotspot: focus_hotspot(h),
                primary=True,
            ).pack(side="right", padx=(8, 0))

            tk.Label(
                title_row,
                text=f"{hotspot['contribution_share']:.1f}% concern contribution",
                bg=CARD_2,
                fg=ACCENT,
                font=(FONT, 8, "bold"),
            ).pack(side="right")

            categories_text = ", ".join(hotspot["categories"][:2])
            distance_text = ""

            if hotspot["average_distance_km"] is not None:
                distance_text = (
                    f" • avg {hotspot['average_distance_km'] * 1000:.0f} m from route"
                )

            tk.Label(
                row,
                text=(
                    f"{hotspot['report_count']} report(s) • "
                    f"{categories_text}{distance_text}"
                ),
                bg=CARD_2,
                fg=MUTED,
                font=(FONT, 8),
                justify="left",
                wraplength=950,
            ).pack(anchor="w", padx=12, pady=(0, 9))

    # --------------------------------------------------------
    # ACTION BAR
    # --------------------------------------------------------

    action_bar = tk.Frame(scroll_content, bg=BG)
    action_bar.pack(fill="x", pady=(0, 18))

    make_button(
        action_bar,
        "Open Advanced Analysis",
        lambda: show_page("advanced"),
        primary=True,
    ).pack(side="left")

    make_button(
        action_bar,
        "Back to Journey",
        lambda: show_page("journey"),
    ).pack(side="left", padx=(8, 0))

    # --------------------------------------------------------
    # TECHNICAL ML INFORMATION IS INTENTIONALLY OMITTED FROM
    # THE DEFAULT VIEW. It remains available in Advanced View.
    # --------------------------------------------------------


def build_results_page():
    render_results_page()


# ============================================================
# REPORT PAGE
# ============================================================

report_page = tk.Frame(content_host, bg=BG)
report_page.grid(row=0, column=0, sticky="nsew")
page_frames["report"] = report_page

report_content = None


def render_report_page():
    global report_content

    clear_frame(report_page)

    scroll_content = create_scrollable(report_page)
    report_content = scroll_content

    tk.Label(
        report_content,
        text="Report an issue",
        bg=BG,
        fg=TEXT,
        font=(FONT, 21, "bold"),
    ).pack(anchor="w", pady=(0, 3))

    tk.Label(
        report_content,
        text="Submit a route-based observation. SafeRoute will analyze the description and check for similar nearby reports.",
        bg=BG,
        fg=MUTED,
        font=(FONT, 9),
        wraplength=1050,
    ).pack(anchor="w", pady=(0, 14))

    if current_route is None:
        tk.Label(
            report_content,
            text="Calculate a route first so the report can be checked against the current journey.",
            bg=CARD,
            fg=WARNING,
            font=(FONT, 10),
            padx=15,
            pady=15,
        ).pack(fill="x")
        return

    form = card(report_content)
    form.pack(fill="x", pady=(0, 12))

    selected_coordinates = {"latitude": None, "longitude": None}
    report_location = {"value": None}

    section_title(
        form,
        "Location",
        "Choose a mapped place or click directly on the route below.",
    )

    location_row = tk.Frame(form, bg=CARD)
    location_row.pack(fill="x", padx=18, pady=5)

    location_entry = make_entry(location_row, from_entry.get())
    location_entry.pack(side="left", fill="x", expand=True, ipady=7)

    suggestion_list = tk.Listbox(
        form,
        bg=CARD_2,
        fg=TEXT,
        selectbackground=ACCENT,
        selectforeground=BG,
        relief="flat",
        height=4,
        font=(FONT, 9),
    )
    suggestion_list.pack(fill="x", padx=18, pady=(5, 5))

    location_status = tk.Label(
        form,
        text="No exact report location selected",
        bg=CARD,
        fg=MUTED,
        font=(FONT, 8),
    )
    location_status.pack(anchor="w", padx=18, pady=(0, 8))

    def report_search():
        query = location_entry.get().strip()
        if not query or query == "Map-selected location":
            location_status.config(text="Enter a local place or click the route map.")
            return

        try:
            route_points = current_route.route_points
            route_bounds = (
                min(point[0] for point in route_points),
                min(point[1] for point in route_points),
                max(point[0] for point in route_points),
                max(point[1] for point in route_points),
            )

            candidates = search_location_candidates(
                query,
                context="Tamil Nadu, India",
                limit=6,
                route_bounds=route_bounds,
            )

            suggestion_list.delete(0, tk.END)
            suggestion_list.candidates = candidates

            for candidate in candidates:
                suggestion_list.insert(
                    tk.END,
                    candidate["display_name"],
                )

            if candidates:
                suggestion_list.selection_set(0)
                location_status.config(
                    text=f"Found {len(candidates)} suggestions.",
                )
            else:
                location_status.config(
                    text="No matching location was found.",
                )

        except Exception as error:
            location_status.config(text=f"Search failed: {error}")

    def apply_report_location():
        candidates = getattr(suggestion_list, "candidates", [])
        selection = suggestion_list.curselection()
        if not candidates or not selection:
            location_status.config(text="Select a suggestion first.")
            return

        candidate = candidates[selection[0]]
        report_location["value"] = candidate
        selected_coordinates["latitude"] = candidate["latitude"]
        selected_coordinates["longitude"] = candidate["longitude"]
        location_entry.delete(0, tk.END)
        location_entry.insert(0, candidate["display_name"])
        location_status.config(text="Exact mapped location selected.")

    make_button(
        location_row,
        "Search",
        report_search,
    ).pack(side="left", padx=(7, 0))

    make_button(
        form,
        "Use Selected Suggestion",
        apply_report_location,
    ).pack(fill="x", padx=18, pady=(0, 10))

    # Provider-aware route preview (interactive OpenStreetMap is the default).
    report_map_card = card(report_content)
    report_map_card.pack(fill="both", pady=(0, 12))

    section_title(
        report_map_card,
        f"{MAP_PROVIDER.upper()} route preview",
        "Use the location search above to choose the exact place for the report.",
    )

    report_map_holder = tk.Frame(report_map_card, bg=CARD_2, height=320)
    report_map_holder.pack(fill="both", expand=True, padx=18, pady=(0, 16))
    report_map_holder.pack_propagate(False)

    report_map_label = tk.Label(
        report_map_holder,
        text=f"Loading {MAP_PROVIDER.upper()} route preview…",
        bg=CARD_2, fg=MUTED, font=(FONT, 9),
    )
    report_map_label.pack(expand=True)

    if MAP_PROVIDER == "google":
        def load_report_map():
            try:
                image_bytes = fetch_google_static_map(current_route_data, width=760, height=320)
                def apply_report_map():
                    if not report_map_label.winfo_exists():
                        return
                    photo = _google_photo_image(image_bytes)
                    report_map_label.config(image=photo, text="")
                    report_map_label.image = photo
                root.after(0, apply_report_map)
            except Exception as error:
                message = str(error)
                root.after(0, lambda message=message: report_map_label.config(
                    text=f"Google route preview unavailable.\n{message}", fg=DANGER
                ) if report_map_label.winfo_exists() else None)
        threading.Thread(target=load_report_map, daemon=True).start()
    else:
        try:
            from tkintermapview import TkinterMapView
            report_map_label.destroy()
            report_route_map = TkinterMapView(report_map_holder, width=760, height=320, corner_radius=0)
            report_route_map.pack(fill="both", expand=True)
            report_route_map.set_path(current_route_data["route_points"])
            report_route_map.set_marker(current_route_data["start"]["latitude"], current_route_data["start"]["longitude"], text="Start")
            report_route_map.set_marker(current_route_data["destination"]["latitude"], current_route_data["destination"]["longitude"], text="Destination")
            points = current_route_data["route_points"]
            report_route_map.set_position(sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
            report_route_map.set_zoom(11)
        except ImportError:
            report_map_label.config(
                text="Install tkintermapview to display the interactive OpenStreetMap route.\nThe route calculation itself is available.",
                fg=WARNING,
            )

    make_button(
        report_map_card,
        "Open route in Google Maps",
        open_current_route_in_google,
    ).pack(anchor="w", padx=18, pady=(0, 12))

    # Issue details
    details = card(report_content)
    details.pack(fill="x", pady=(0, 12))

    section_title(
        details,
        "Issue details",
        "SafeRoute AI can suggest a category and severity from the description.",
    )

    tk.Label(details, text="Category", bg=CARD, fg=MUTED, font=(FONT, 9, "bold")).pack(anchor="w", padx=18, pady=(3, 3))

    category_box = ttk.Combobox(
        details,
        values=[
            "Poor Lighting",
            "Construction",
            "Blocked Path",
            "Road Hazard",
            "Flooding",
            "Traffic",
            "Other",
        ],
        width=38,
        state="readonly",
        style="Safe.TCombobox",
    )
    category_box.pack(anchor="w", padx=18, pady=(0, 10))
    category_box.set("Poor Lighting")

    tk.Label(details, text="Severity", bg=CARD, fg=MUTED, font=(FONT, 9, "bold")).pack(anchor="w", padx=18, pady=(0, 3))

    severity_box = ttk.Combobox(
        details,
        values=["1 - Low", "2 - Moderate", "3 - High"],
        width=38,
        state="readonly",
        style="Safe.TCombobox",
    )
    severity_box.pack(anchor="w", padx=18, pady=(0, 10))
    severity_box.set("2 - Moderate")

    tk.Label(details, text="Description", bg=CARD, fg=MUTED, font=(FONT, 9, "bold")).pack(anchor="w", padx=18, pady=(0, 3))

    description_box = tk.Text(
        details,
        height=7,
        bg=CARD_2,
        fg=TEXT,
        insertbackground=TEXT,
        relief="flat",
        font=(FONT, 10),
        wrap="word",
    )
    description_box.pack(fill="x", padx=18, pady=(0, 10))

    ai_status = tk.Label(
        details,
        text="AI suggestion: waiting for description",
        bg=CARD,
        fg=MUTED,
        font=(FONT, 8),
        justify="left",
        wraplength=1000,
    )
    ai_status.pack(anchor="w", padx=18, pady=(0, 8))

    def suggest_with_ai():
        description = description_box.get("1.0", tk.END).strip()
        if not description:
            ai_status.config(text="Enter a description first.", fg=WARNING)
            return

        try:
            result = report_ai.analyze_report_against_history(
                description,
                get_reports(),
                category=category_box.get().strip(),
            )

            severity_labels = {
                1: "1 - Low",
                2: "2 - Moderate",
                3: "3 - High",
            }

            category_box.set(result["category"])
            severity_box.set(severity_labels[result["suggested_severity"]])

            similar_reports = result.get("similar_reports", [])
            similarity_text = "No strong similar report found"
            if similar_reports:
                similarity_text = (
                    f"Possible similar report: {similar_reports[0]['similarity'] * 100:.0f}%"
                )

            ai_status.config(
                text=(
                    f"AI suggestion: {result['category']} "
                    f"({result['category_confidence'] * 100:.0f}% confidence) • "
                    f"Suggested severity: {result['suggested_severity']}/3 • "
                    f"{similarity_text}"
                ),
                fg=ACCENT,
            )

        except Exception as error:
            ai_status.config(text=f"AI analysis failed: {error}", fg=DANGER)

    make_button(
        details,
        "Suggest Category & Severity",
        suggest_with_ai,
        primary=True,
    ).pack(anchor="w", padx=18, pady=(0, 12))

    def submit_report_inline():
        location = location_entry.get().strip()
        category = category_box.get().strip()
        severity_text = severity_box.get().strip()
        description = description_box.get("1.0", tk.END).strip()

        if not location or location == "Map-selected location":
            if selected_coordinates["latitude"] is None:
                ai_status.config(text="Select an exact report location first.", fg=WARNING)
                return

        if not category or not severity_text or not description:
            ai_status.config(text="Complete category, severity, and description.", fg=WARNING)
            return

        latitude = selected_coordinates["latitude"]
        longitude = selected_coordinates["longitude"]

        if latitude is None or longitude is None:
            ai_status.config(
                text="Choose a suggestion or click a location directly on the route map.",
                fg=WARNING,
            )
            return

        root.config(cursor="watch")
        try:
            test_incident = type("TemporaryIncident", (), {})()
            test_incident.latitude = latitude
            test_incident.longitude = longitude

            analyzer = SafetyAnalyzer([])
            match = analyzer.find_closest_segment(test_incident, current_route)

            if match is None:
                ai_status.config(
                    text="The selected point is too far from the current route.",
                    fg=WARNING,
                )
                return

            matched_segment = match[0]["name"]
            distance_m = round(match[1] * 1000)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            severity = int(severity_text[0])

            existing_reports = get_reports()
            similar_reports = report_ai.find_similar_reports(
                description,
                existing_reports,
                category=category,
                threshold=0.62,
            )

            nearby_similar = []
            for match_info in similar_reports:
                report = match_info["report"]
                existing_lat = getattr(report, "latitude", None)
                existing_lon = getattr(report, "longitude", None)

                if existing_lat is None or existing_lon is None:
                    continue

                distance = analyzer.calculate_distance_km(
                    latitude,
                    longitude,
                    existing_lat,
                    existing_lon,
                )

                if distance <= 0.50:
                    match_info["distance_km"] = distance
                    nearby_similar.append(match_info)

            if nearby_similar:
                best = max(
                    nearby_similar,
                    key=lambda item: item["similarity"],
                )
                report = best["report"]
                ai_status.config(
                    text=(
                        f"Possible nearby similar report: "
                        f"{best['similarity'] * 100:.0f}% similar, "
                        f"{best['distance_km'] * 1000:.0f} m away. "
                        "Click Submit again to store this as an additional observation."
                    ),
                    fg=WARNING,
                )

                already_warned = getattr(submit_report_inline, "similar_warning", False)
                if not already_warned:
                    submit_report_inline.similar_warning = True
                    return

            add_report(
                location,
                category,
                severity,
                description,
                timestamp,
                latitude,
                longitude,
            )

            submit_report_inline.similar_warning = False
            ai_status.config(
                text=(
                    "Report submitted successfully. "
                    f"Matched {matched_segment} • approximately {distance_m} m from route."
                ),
                fg=SUCCESS,
            )
            description_box.delete("1.0", tk.END)
            set_status("Community report added to the database.", "success")

        except Exception as error:
            ai_status.config(text=f"Report submission failed: {error}", fg=DANGER)
        finally:
            root.config(cursor="")

    make_button(
        details,
        "Submit Community Report",
        submit_report_inline,
        primary=True,
    ).pack(anchor="w", padx=18, pady=(0, 18))


# ============================================================
# ADVANCED PAGE
# ============================================================

advanced_page = tk.Frame(content_host, bg=BG)
advanced_page.grid(row=0, column=0, sticky="nsew")
page_frames["advanced"] = advanced_page


def render_advanced_page():
    clear_frame(advanced_page)

    scroll_content = create_scrollable(advanced_page)

    tk.Label(
        scroll_content,
        text="Advanced analysis",
        bg=BG,
        fg=TEXT,
        font=(FONT, 21, "bold"),
    ).pack(anchor="w", pady=(0, 3))

    tk.Label(
        scroll_content,
        text="Technical view of the SafeRoute decision pipeline.",
        bg=BG,
        fg=MUTED,
        font=(FONT, 9),
    ).pack(anchor="w", pady=(0, 14))

    if not current_analysis:
        tk.Label(
            scroll_content,
            text="Run a journey analysis first.",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 10),
            padx=18,
            pady=18,
        ).pack(fill="x")
        return

    data = current_analysis

    def technical_card(title, rows):
        frame = card(scroll_content)
        frame.pack(fill="x", pady=(0, 12))
        section_title(frame, title)

        for label, value in rows:
            row = tk.Frame(frame, bg=CARD)
            row.pack(fill="x", padx=18, pady=3)

            tk.Label(
                row,
                text=label,
                bg=CARD,
                fg=MUTED,
                font=(FONT, 9),
                width=28,
                anchor="w",
            ).pack(side="left")

            tk.Label(
                row,
                text=value,
                bg=CARD,
                fg=TEXT,
                font=(FONT, 9, "bold"),
                anchor="w",
                justify="left",
                wraplength=700,
            ).pack(side="left", fill="x", expand=True)

        return frame

    technical_card(
        "Core safety engine",
        [
            ("Safety Concern Score", f"{data['score']}/10"),
            ("Assessment", data["assessment"]),
            ("Data Confidence", data["confidence"]),
            ("Relevant Reports", str(len(data["relevant_reports"]))),
            ("Journey Type", data["journey_type"]),
            ("Journey Time", data["journey_time"]),
        ],
    )

    technical_card(
        "Prototype ML layer",
        [
            ("ML Risk Indicator", f"{data['ml_risk']}/10"),
            ("Status", "Experimental prototype — supporting signal only"),
            ("Factors", "; ".join(data["ml_factors"])),
        ],
    )

    hotspot_rows = []
    for hotspot in data["hotspots"]["hotspots"]:
        hotspot_rows.append(
            (
                hotspot["segment"],
                (
                    f"{hotspot['report_count']} report(s) • "
                    f"{', '.join(hotspot['categories'])} • "
                    f"{hotspot['contribution_share']:.1f}% contribution"
                ),
            )
        )

    if not hotspot_rows:
        hotspot_rows.append(("Hotspots", "No hotspot data available"))

    technical_card("Route hotspot engine", hotspot_rows)

    evidence = card(scroll_content)
    evidence.pack(fill="x", pady=(0, 12))
    section_title(evidence, "Contextual briefing evidence")

    for item in data["contextual_briefing"]["evidence"]:
        tk.Label(
            evidence,
            text=f"• {item}",
            bg=CARD,
            fg=TEXT,
            font=(FONT, 9),
            justify="left",
            wraplength=1000,
        ).pack(anchor="w", padx=18, pady=3)


# ============================================================
# COMMUNITIES PAGE
# ============================================================

communities_page = tk.Frame(content_host, bg=BG)
communities_page.grid(row=0, column=0, sticky="nsew")
page_frames["communities"] = communities_page


def render_communities_page():
    clear_frame(communities_page)
    scroll = create_scrollable(communities_page)

    tk.Label(scroll, text="Communities", bg=BG, fg=TEXT, font=(FONT, 21, "bold")).pack(anchor="w", pady=(0, 3))
    tk.Label(
        scroll,
        text="Community observations help describe local conditions. Reports are user-submitted and are not automatically verified.",
        bg=BG, fg=MUTED, font=(FONT, 9), wraplength=1050, justify="left",
    ).pack(anchor="w", pady=(0, 12))

    mode_text = (
        f"Shared feed connected: {community_service.api_url}"
        if community_service.is_shared
        else "Local-only mode · reports are stored on this computer and are not shared with other installations."
    )
    mode_color = SUCCESS if community_service.is_shared else WARNING
    tk.Label(scroll, text=mode_text, bg=CARD, fg=mode_color, font=(FONT, 9, "bold"), padx=14, pady=10, wraplength=1000, justify="left").pack(fill="x", pady=(0, 12))

    feed_card = card(scroll)
    feed_card.pack(fill="x", pady=(0, 12))
    section_title(feed_card, "Community feed", "Filter recent local observations or narrow the list to reports near your currently calculated route.")

    controls = tk.Frame(feed_card, bg=CARD)
    controls.pack(fill="x", padx=18, pady=(4, 10))
    category_filter = ttk.Combobox(
        controls,
        values=["All categories", "Poor Lighting", "Construction", "Blocked Path", "Road Hazard", "Flooding", "Traffic", "Other"],
        state="readonly", width=22, style="Safe.TCombobox",
    )
    category_filter.set("All categories")
    category_filter.pack(side="left", padx=(0, 8))
    along_route_var = tk.BooleanVar(value=False)
    along_route_check = tk.Checkbutton(
        controls, text="Along current route", variable=along_route_var,
        bg=CARD, fg=TEXT, selectcolor=CARD_2, activebackground=CARD,
        activeforeground=TEXT, font=(FONT, 9),
        state=(tk.NORMAL if current_route_data else tk.DISABLED),
    )
    along_route_check.pack(side="left", padx=(0, 8))
    near_home_var = tk.BooleanVar(value=False)
    near_home_check = tk.Checkbutton(
        controls, text="Near home area (5 km)", variable=near_home_var,
        bg=CARD, fg=TEXT, selectcolor=CARD_2, activebackground=CARD,
        activeforeground=TEXT, font=(FONT, 9),
    )
    near_home_check.pack(side="left")
    home_center = {"point": None, "loading": False}
    feed_status = tk.Label(feed_card, text="", bg=CARD, fg=MUTED, font=(FONT, 8))
    feed_status.pack(anchor="w", padx=18, pady=(0, 5))
    feed_list = tk.Frame(feed_card, bg=CARD)
    feed_list.pack(fill="x", padx=18, pady=(0, 16))

    def refresh_feed():
        for child in feed_list.winfo_children():
            child.destroy()
        try:
            reports = community_service.get_reports(include_demo=False, include_inactive=True)
            selected_category = category_filter.get()
            if selected_category != "All categories":
                reports = [r for r in reports if r.category == selected_category]
            if near_home_var.get():
                home_area = get_profile().get("home_area", "").strip()
                if not home_area:
                    reports = []
                    feed_status.config(text="Set a home area in Profile to use the nearby filter.", fg=WARNING)
                elif home_center["point"] is None:
                    if not home_center["loading"]:
                        home_center["loading"] = True
                        feed_status.config(text="Finding your saved home area…", fg=MUTED)
                        def find_home_center():
                            try:
                                point = geocode_location(home_area, context="Tamil Nadu, India")
                                def finish_home_search():
                                    home_center["point"] = (float(point["latitude"]), float(point["longitude"]))
                                    home_center["loading"] = False
                                    refresh_feed()
                                root.after(0, finish_home_search)
                            except Exception as error:
                                def fail_home_search(message=str(error)):
                                    home_center["loading"] = False
                                    feed_status.config(text=f"Could not locate home area: {message}", fg=DANGER)
                                root.after(0, fail_home_search)
                        threading.Thread(target=find_home_center, daemon=True).start()
                    return
                else:
                    reports = community_service.filter_near_location(reports, home_center["point"], radius_km=5.0)
            if along_route_var.get():
                if not current_route_data:
                    reports = []
                else:
                    reports = community_service.filter_along_route(
                        reports, current_route_data.get("route_points", []), radius_km=0.75
                    )
            if not (near_home_var.get() and not get_profile().get("home_area", "").strip()):
                feed_status.config(text=f"{len(reports)} report(s) · Demo records excluded · No reports means insufficient data, not proof of safety.")
            if not reports:
                tk.Label(feed_list, text="No matching community reports.", bg=CARD_2, fg=MUTED, font=(FONT, 10), padx=14, pady=18).pack(fill="x")
                return
            for report in reports[:60]:
                item = tk.Frame(feed_list, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
                item.pack(fill="x", pady=4)
                top = tk.Frame(item, bg=CARD_2)
                top.pack(fill="x", padx=12, pady=(9, 2))
                tk.Label(top, text=f"{report.category}  ·  Severity {report.severity}/3", bg=CARD_2, fg=TEXT, font=(FONT, 10, "bold")).pack(side="left")
                status_color = SUCCESS if report.status == "Confirmed" else WARNING if report.status in {"Reported", "Under Review"} else MUTED
                tk.Label(top, text=report.status, bg=CARD_2, fg=status_color, font=(FONT, 8, "bold")).pack(side="right")
                tk.Label(item, text=report.location, bg=CARD_2, fg=ACCENT, font=(FONT, 9, "bold")).pack(anchor="w", padx=12, pady=(2, 2))
                tk.Label(item, text=report.description or "No description provided.", bg=CARD_2, fg=TEXT, font=(FONT, 9), justify="left", wraplength=900).pack(anchor="w", padx=12, pady=2)
                distance_text = f" · {report.matched_distance_km * 1000:.0f} m from route" if getattr(report, "matched_distance_km", None) is not None and along_route_var.get() else ""
                tk.Label(item, text=f"{report.timestamp} · {report.author}{distance_text}", bg=CARD_2, fg=MUTED, font=(FONT, 8)).pack(anchor="w", padx=12, pady=(3, 9))
        except Exception as error:
            feed_status.config(text=f"Could not load community feed: {error}", fg=DANGER)

    make_button(controls, "Refresh", refresh_feed).pack(side="right")
    category_filter.bind("<<ComboboxSelected>>", lambda event: refresh_feed())
    along_route_check.config(command=refresh_feed)
    near_home_check.config(command=refresh_feed)
    refresh_feed()

    submit_card = card(scroll)
    submit_card.pack(fill="x", pady=(0, 12))
    section_title(submit_card, "Share an observation", "A location match is required so reports can be compared with routes. Avoid including private personal information in descriptions.")

    location_row = tk.Frame(submit_card, bg=CARD)
    location_row.pack(fill="x", padx=18, pady=(4, 5))
    location_entry = make_entry(location_row)
    location_entry.pack(side="left", fill="x", expand=True, ipady=7)
    candidate_box = ttk.Combobox(submit_card, values=[], state="readonly", style="Safe.TCombobox")
    candidate_box.pack(fill="x", padx=18, pady=4)
    selected_location = {"candidate": None}
    location_status = tk.Label(submit_card, text="Search for a location to geotag your report.", bg=CARD, fg=MUTED, font=(FONT, 8))
    location_status.pack(anchor="w", padx=18, pady=(2, 6))

    def find_community_location():
        query = location_entry.get().strip()
        if len(query) < 2:
            location_status.config(text="Enter at least two characters.", fg=WARNING)
            return
        location_status.config(text=f"Searching {MAP_PROVIDER.upper()}…", fg=MUTED)
        root.config(cursor="watch")
        def worker():
            try:
                candidates = search_location_candidates(query, context="Tamil Nadu, India", limit=6)
                def apply():
                    candidate_box.candidates = candidates
                    candidate_box["values"] = [c.get("display_name", "Location") for c in candidates]
                    if candidates:
                        candidate_box.current(0)
                        selected_location["candidate"] = candidates[0]
                        location_status.config(text="Select the correct result, then submit.", fg=SUCCESS)
                    else:
                        location_status.config(text="No matching location found. Try a nearby landmark.", fg=WARNING)
                    root.config(cursor="")
                root.after(0, apply)
            except Exception as error:
                message = str(error)
                root.after(0, lambda message=message: (location_status.config(text=f"Location search failed: {message}", fg=DANGER), root.config(cursor="")))
        threading.Thread(target=worker, daemon=True).start()

    def choose_community_candidate(event=None):
        candidates = getattr(candidate_box, "candidates", [])
        index = candidate_box.current()
        selected_location["candidate"] = candidates[index] if 0 <= index < len(candidates) else None

    candidate_box.bind("<<ComboboxSelected>>", choose_community_candidate)
    make_button(location_row, "Find location", find_community_location).pack(side="left", padx=(7, 0))

    fields = tk.Frame(submit_card, bg=CARD)
    fields.pack(fill="x", padx=18, pady=5)
    category_box = ttk.Combobox(fields, values=["Poor Lighting", "Construction", "Blocked Path", "Road Hazard", "Flooding", "Traffic", "Other"], state="readonly", width=22, style="Safe.TCombobox")
    category_box.set("Poor Lighting")
    category_box.pack(side="left", padx=(0, 8))
    severity_box = ttk.Combobox(fields, values=["1 - Low", "2 - Moderate", "3 - High"], state="readonly", width=15, style="Safe.TCombobox")
    severity_box.set("2 - Moderate")
    severity_box.pack(side="left")
    description_box = tk.Text(submit_card, height=4, bg=CARD_2, fg=TEXT, insertbackground=TEXT, relief="flat", font=(FONT, 9), wrap="word")
    description_box.pack(fill="x", padx=18, pady=(5, 8))
    submit_status = tk.Label(submit_card, text="Submitted reports start as 'Reported' and are not automatically verified.", bg=CARD, fg=MUTED, font=(FONT, 8), wraplength=950, justify="left")
    submit_status.pack(anchor="w", padx=18, pady=(0, 8))

    def submit_community_observation():
        candidate = selected_location.get("candidate")
        description = description_box.get("1.0", tk.END).strip()
        if not candidate:
            submit_status.config(text="Find and select an exact location first.", fg=WARNING)
            return
        if len(description) < 3:
            submit_status.config(text="Add a short description (at least 3 characters).", fg=WARNING)
            return
        profile = get_profile()
        try:
            community_service.submit_report(
                location=candidate.get("display_name", location_entry.get().strip()),
                category=category_box.get(),
                severity=int(severity_box.get()[0]),
                description=description,
                latitude=float(candidate["latitude"]),
                longitude=float(candidate["longitude"]),
                author=profile.get("display_name", "Community member"),
            )
            submit_status.config(text="Report submitted. It is marked Reported until reviewed.", fg=SUCCESS)
            description_box.delete("1.0", tk.END)
            refresh_feed()
        except Exception as error:
            submit_status.config(text=f"Could not submit report: {error}", fg=DANGER)

    make_button(submit_card, "Submit community report", submit_community_observation, primary=True).pack(anchor="w", padx=18, pady=(0, 16))


# ============================================================
# PROFILE PAGE
# ============================================================

profile_page = tk.Frame(content_host, bg=BG)
profile_page.grid(row=0, column=0, sticky="nsew")
page_frames["profile"] = profile_page


def render_profile_page():
    clear_frame(profile_page)
    scroll = create_scrollable(profile_page)
    profile = get_profile()

    tk.Label(scroll, text="Profile", bg=BG, fg=TEXT, font=(FONT, 21, "bold")).pack(anchor="w", pady=(0, 3))
    tk.Label(scroll, text="Manage the local SafeRoute profile used to label new community observations.", bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", pady=(0, 14))

    profile_card = card(scroll)
    profile_card.pack(fill="x", pady=(0, 12))
    section_title(profile_card, "Your details", "Profile settings are stored locally on this computer. The display-name option controls the author label on new reports; it does not create an online account.")
    tk.Label(profile_card, text="Display name", bg=CARD, fg=MUTED, font=(FONT, 9, "bold")).pack(anchor="w", padx=18, pady=(5, 3))
    display_name_entry = make_entry(profile_card, profile.get("display_name", "SafeRoute user"))
    display_name_entry.pack(fill="x", padx=18, pady=(0, 10), ipady=7)
    tk.Label(profile_card, text="Home area (optional)", bg=CARD, fg=MUTED, font=(FONT, 9, "bold")).pack(anchor="w", padx=18, pady=(0, 3))
    home_area_entry = make_entry(profile_card, profile.get("home_area", ""))
    home_area_entry.pack(fill="x", padx=18, pady=(0, 10), ipady=7)
    share_name_var = tk.BooleanVar(value=profile.get("preferences", {}).get("share_display_name", True))
    share_name_check = tk.Checkbutton(
        profile_card, text="Show my display name on new community reports",
        variable=share_name_var, bg=CARD, fg=TEXT, selectcolor=CARD_2,
        activebackground=CARD, activeforeground=TEXT, font=(FONT, 9),
    )
    share_name_check.pack(anchor="w", padx=18, pady=(0, 8))
    save_status = tk.Label(profile_card, text="", bg=CARD, fg=MUTED, font=(FONT, 8))
    save_status.pack(anchor="w", padx=18, pady=(0, 5))

    def save_profile_changes():
        try:
            save_profile(
                display_name_entry.get(),
                home_area_entry.get(),
                {"share_display_name": bool(share_name_var.get())},
            )
            save_status.config(text="Profile saved locally.", fg=SUCCESS)
        except Exception as error:
            save_status.config(text=str(error), fg=DANGER)

    make_button(profile_card, "Save profile", save_profile_changes, primary=True).pack(anchor="w", padx=18, pady=(0, 16))

    stats_card = card(scroll)
    stats_card.pack(fill="x", pady=(0, 12))
    section_title(stats_card, "Contribution overview")
    current_name = profile.get("display_name", "SafeRoute user")
    try:
        visible_reports = get_reports(include_inactive=True)
        contribution_count = sum(1 for report in visible_reports if report.author == current_name and not report.is_demo)
    except Exception:
        contribution_count = "Unavailable" if community_service.is_shared else count_reports_by_author(current_name)
    saved = get_saved_journeys()
    stats = tk.Frame(stats_card, bg=CARD)
    stats.pack(fill="x", padx=18, pady=(5, 16))
    for label, value in (("Reports submitted", contribution_count), ("Saved journeys", len(saved)), ("Storage", "Shared" if community_service.is_shared else "This device")):
        block = tk.Frame(stats, bg=CARD_2, padx=14, pady=12)
        block.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(block, text=str(value), bg=CARD_2, fg=ACCENT, font=(FONT, 16, "bold")).pack(anchor="w")
        tk.Label(block, text=label, bg=CARD_2, fg=MUTED, font=(FONT, 8)).pack(anchor="w")

    journeys_card = card(scroll)
    journeys_card.pack(fill="x", pady=(0, 12))
    section_title(journeys_card, "Saved journeys", "Saved journey details are local to this installation.")
    if current_route_data and selected_locations.get("from") and selected_locations.get("to"):
        def save_current_journey():
            start = selected_locations["from"]
            destination = selected_locations["to"]
            try:
                save_journey(
                    f"{start.get('display_name', 'Start')} → {destination.get('display_name', 'Destination')}",
                    start.get("display_name", "Start"), destination.get("display_name", "Destination"),
                    (start.get("latitude"), start.get("longitude")),
                    (destination.get("latitude"), destination.get("longitude")),
                    current_route_data.get("distance_km"), current_route_data.get("duration_min"),
                )
                render_profile_page()
            except Exception as error:
                save_status.config(text=f"Could not save journey: {error}", fg=DANGER)
        make_button(journeys_card, "Save current journey", save_current_journey, primary=True).pack(anchor="w", padx=18, pady=(0, 10))
    if not saved:
        tk.Label(journeys_card, text="No saved journeys yet.", bg=CARD, fg=MUTED, font=(FONT, 9), padx=18, pady=12).pack(anchor="w")
    else:
        for journey in saved[:20]:
            row = tk.Frame(journeys_card, bg=CARD_2)
            row.pack(fill="x", padx=18, pady=4)
            distance = journey.get("distance_km")
            duration = journey.get("duration_min")
            suffix = f" · {distance} km · {duration} min" if distance is not None and duration is not None else ""
            tk.Label(row, text=journey["name"] + suffix, bg=CARD_2, fg=TEXT, font=(FONT, 9, "bold"), padx=10, pady=9, wraplength=900, justify="left").pack(fill="x")

    note = tk.Label(scroll, text="Privacy note: SafeRoute is a prototype. The profile is a local preference record, not verified identity or authentication.", bg=BG, fg=MUTED, font=(FONT, 8), wraplength=1000, justify="left")
    note.pack(anchor="w", pady=(3, 12))


# ============================================================
# PAGE GRID + INITIAL STATE
# ============================================================

content_host.grid_rowconfigure(0, weight=1)
content_host.grid_columnconfigure(0, weight=1)

set_nav_active("journey")
journey_page.tkraise()

root.mainloop()
