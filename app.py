# app.py
import os
import re
import math
import json
import time
import requests
import numpy as np
import pandas as pd
import streamlit as st

# -------------------------- Defaults / constants --------------------------
DEFAULT_SERVER = "ts4.x1.international.travian.com"
GOOGLE_SHEET_ID_DEFAULT = "1Ev6h8-rTbCHoK2vNEyYpBSVs4AvJ43XzPQ3CuC6sTSw"
GOOGLE_SHEET_NAME_DEFAULT = "cookie"

unit_mapping = {
    "u31": ("rat", 160),
    "u32": ("spider", 160),
    "u33": ("serpent", 160),
    "u34": ("bat", 160),
    "u35": ("wild boar", 320),
    "u36": ("wolf", 320),
    "u37": ("bear", 480),
    "u38": ("croco", 480),
    "u39": ("tiger", 480),
    "u40": ("elephant", 800),
}
xp_per_unit = [1, 1, 1, 1, 2, 2, 3, 3, 3, 5]


# -------------------------- Core helpers (unchanged logic) --------------------------
def calculate_distance(x1, y1, x2, y2):
    return round(math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2), 2)


def extract_data(entry: str, x_vil: int, y_vil: int):
    x_match = re.search(r'"x":\s*(-?\d+)', entry)
    y_match = re.search(r'"y":\s*(-?\d+)', entry)
    if not (x_match and y_match):
        return None
    x_coord = int(x_match.group(1))
    y_coord = int(y_match.group(1))

    distance = calculate_distance(x_coord, y_coord, x_vil, y_vil)

    units = re.findall(
        r'class="unit u(3[1-9]|40)"><\/i><span class="value ">(\d+)<\/span>', entry
    )

    unit_counts = [0] * 10
    total_points = 0
    for unit_id, count in units:
        idx = int(unit_id) - 31
        count = int(count)
        unit_counts[idx] = count
        points_per_unit = unit_mapping[f"u{unit_id}"][1]
        total_points += count * points_per_unit

    return {
        "x": x_coord,
        "y": y_coord,
        "distance": distance,
        "total_points": total_points,
        "unit_counts": unit_counts,
    }


def post_request(server: str, x: int, y: int, cookie: str, fullmap: bool = False) -> str:
    url = f"https://{server}/api/v1/map/position"
    headers = {
        "authority": f"{server}",
        "method": "POST",
        "path": "/api/v1/map/position",
        "scheme": "https",
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json; charset=UTF-8",
        "cookie": cookie,
        "origin": f"https://{server}",
        "referer": f"https://{server}/karte.php",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"}',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "x-requested-with": "XMLHttpRequest",
        "x-version": "52.8",
    }

    if fullmap:
        texts = ""
        # small window to reduce traffic; tweak as you like
        for xi in range(x - 90, x + 90, 30):
            for yi in range(y - 90, y + 90, 30):
                payload = {"data": {"x": xi, "y": yi, "zoomLevel": 3, "ignorePositions": []}}
                r = requests.post(url, headers=headers, json=payload, timeout=25)
                r.raise_for_status()
                texts += r.text
                time.sleep(0.15)  # be polite, avoid rate limiting
        return texts

    payload = {"data": {"x": x, "y": y, "zoomLevel": 3, "ignorePositions": []}}
    r = requests.post(url, headers=headers, json=payload, timeout=25)
    r.raise_for_status()
    return r.text


def process_map_data(server: str, x_vil: int, y_vil: int, cookie: str, fullmap: bool):
    data = post_request(server, x_vil, y_vil, cookie, fullmap)
    if "Unauth" in data:
        # Upstream returns text blobs; this is a heuristic
        raise RuntimeError("Cookie invalid/expired (found 'Unauth' in response).")

    cleaned = data.replace("\\", "")
    chunks = cleaned.split('"position":{')
    filtered = [c for c in chunks if "animal" in c]
    filtered = list(set(filtered))
    processed = [extract_data(entry, x_vil, y_vil) for entry in filtered]
    processed = [p for p in processed if p is not None]
    return processed


def get_calculation_result(animals, hero_atk_pts):
    url = "http://travian.kirilloid.ru/awar2.php"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "http://travian.kirilloid.ru",
        "Referer": "http://travian.kirilloid.ru/warsim2.php",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    }

    payload = {
        "data": json.dumps(
            [
                {"p": 500, "r": 3},
                {"r": 3, "u": animals, "U": [0, 0, 0, 0, 0, 0, 0, 0], "side": "def"},
                {
                    "r": 1,
                    "R": 1,
                    "u": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                    "U": [0, 0, 0, 0, 0, 0, 0, 0],
                    "h": True,
                    "s": [100, 0, hero_atk_pts, 10],
                    "c": True,
                    "i": [0, 0, 85, 0, 0, 25],
                    "I": [0, 0],
                    "b": [0, 0],
                    "side": "off",
                },
            ]
        ),
        "mode": 9,
    }

    r = requests.post(url, headers=headers, data=payload, timeout=20)
    r.raise_for_status()
    data = r.json()[1]
    losses = data["losses"]
    return losses[0]  # fraction (e.g. 0.23)


def read_cookie_from_sheet(sheet_id: str, sheet_name: str) -> str:
    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    )
    df = pd.read_csv(csv_url, header=None)
    return str(df.values[0][0])


def find_oases(
    x_vil: int,
    y_vil: int,
    hero_atk_pts: int,
    *,
    server: str = DEFAULT_SERVER,
    cookie: str | None = None,
    cookie_sheet_id: str = GOOGLE_SHEET_ID_DEFAULT,
    cookie_sheet_name: str = GOOGLE_SHEET_NAME_DEFAULT,
    fullmap: bool = False,
    hero_speed: int = 17,
    borstplaat: int = 0,
    max_hp_lost_pct: int = 500,
    min_resource_score: float = 500.0,
    max_distance: float = 30.0,
):
    if cookie is None:
        cookie = read_cookie_from_sheet(cookie_sheet_id, cookie_sheet_name)

    entries = process_map_data(server, x_vil, y_vil, cookie, fullmap)

    results = []
    for entry in entries:
        if entry["distance"] >= max_distance:
            continue

        animals = entry["unit_counts"]
        hp_frac = get_calculation_result(animals, hero_atk_pts)
        if hp_frac is None:
            continue

        hp_lost_after_armor = max(0, int(hp_frac * 100) - borstplaat)
        entry["hp_lost"] = hp_lost_after_armor

        actual_points = 0
        total_xp = 0
        for i, count in enumerate(animals):
            units_killed = round(count * (1 - hp_frac))
            points_per_unit = unit_mapping[f"u{31 + i}"][1]
            actual_points += units_killed * points_per_unit
            total_xp += units_killed * xp_per_unit[i]

        entry["total_res"] = actual_points
        entry["resource_score"] = round((actual_points * hero_speed) / entry["distance"], 0) / 2
        entry["XP"] = total_xp

        if entry["hp_lost"] < max_hp_lost_pct and entry["resource_score"] > min_resource_score:
            results.append(entry)

    results.sort(key=lambda x: x["resource_score"], reverse=True)
    return results


# -------------------------- Streamlit UI --------------------------
st.set_page_config(page_title="Oasis Finder", layout="wide")

st.title("Oasis Finder")

with st.expander("Inputs"):
    c1, c2, c3, c4 = st.columns(4)
    x_vil = c1.number_input("Village X (x_vil)", value=15, step=1)
    y_vil = c2.number_input("Village Y (y_vil)", value=-66, step=1)
    hero_atk_pts = c3.number_input("Hero Attack Points", value=12, step=1, min_value=0)
    server = c4.text_input("Server", value=DEFAULT_SERVER)

    c5, c6 = st.columns(2)
    cookie_mode = c5.radio(
        "Cookie Source",
        options=["Paste manually", "Google Sheet"],
        index=1,
        horizontal=True,
    )
    cookie = None
    if cookie_mode == "Paste manually":
        cookie = c6.text_area("Paste cookie here", value="", height=80)
    else:
        sheet_id = st.text_input("Google Sheet ID", value=GOOGLE_SHEET_ID_DEFAULT)
        sheet_name = st.text_input("Sheet name", value=GOOGLE_SHEET_NAME_DEFAULT)

    c7, c8, c9, c10 = st.columns(4)
    fullmap = c7.checkbox("Scan 180×180 (fullmap window)", value=False)
    hero_speed = c8.number_input("Hero speed", value=17, step=1, min_value=1)
    borstplaat = c9.number_input("Armor reduction (borstplaat)", value=0, step=1, min_value=0)
    max_distance = c10.number_input("Max distance", value=30.0, step=1.0, min_value=1.0)

    c11, c12 = st.columns(2)
    max_hp_lost_pct = c11.number_input("Max hp_lost (%) threshold", value=500, step=10, min_value=0)
    min_resource_score = c12.number_input("Min GS/u", value=500.0, step=10.0, min_value=0.0)

run_btn = st.button("Find Oases")

st.markdown("---")

# Output columns
left, right = st.columns([1, 1.2])

if run_btn:
    try:
        with st.spinner("Querying map and computing results..."):
            # Try to bypass proxies in some environments
            os.environ["NO_PROXY"] = "*"
            os.environ["no_proxy"] = "*"

            results = find_oases(
                x_vil=x_vil,
                y_vil=y_vil,
                hero_atk_pts=hero_atk_pts,
                server=server,
                cookie=cookie if cookie_mode == "Paste manually" and cookie else None,
                cookie_sheet_id=sheet_id if cookie_mode == "Google Sheet" else GOOGLE_SHEET_ID_DEFAULT,
                cookie_sheet_name=sheet_name if cookie_mode == "Google Sheet" else GOOGLE_SHEET_NAME_DEFAULT,
                fullmap=fullmap,
                hero_speed=hero_speed,
                borstplaat=borstplaat,
                max_hp_lost_pct=max_hp_lost_pct,
                min_resource_score=min_resource_score,
                max_distance=max_distance,
            )

        if not results:
            st.warning("No oasis with animals found (or none matched your filters).")
        else:
            # Formatted print-style lines (left panel) – mirrors your original output
            left.subheader("Formatted output")
            formatted = []
            for e in results:
                formatted.append(
                    f"x: {e['x']}, y: {e['y']}, distance: {round(e['distance'],1)},\t"
                    f"GS/u: {e['resource_score']},\t XP: {e['XP']},\t hp_lost: {max(0, e['hp_lost'])},\t GS: {max(0, e['total_res'])}"
                )
            left.code("\n".join(formatted), language="text")

            # Data table (right panel)
            right.subheader("Results table")
            df = pd.DataFrame(results).drop(columns=["unit_counts"], errors="ignore")
            right.dataframe(df, use_container_width=True)

            # Download
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="oases.csv",
                mime="text/csv",
            )

    except requests.exceptions.ProxyError as e:
        st.error(
            "Proxy blocked the request (common on PythonAnywhere free). "
            "Run locally or on a host with unrestricted outbound traffic."
        )
        st.exception(e)
    except requests.HTTPError as e:
        st.error(f"HTTP error from server: {e}")
        st.exception(e)
    except Exception as e:
        st.error("Unexpected error.")
        st.exception(e)

# Footnote / note
st.caption(
    "Note: Some hosts (e.g., PythonAnywhere free) block outgoing requests to game servers. "
    "For reliable results, run locally or on a VPS with unrestricted internet."
)
