import os
import json
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────
#  VOV Traffic Scraper
# ──────────────────────────────────────────────

class VOVTrafficScraper:
    """
    Fetches the latest traffic news from VOV Giao thong.
    Supports both RSS feed and direct web scraping.
    """

    RSS_URL = "https://vovgiaothong.vn/rss"
    WEB_URL = "https://vovgiaothong.vn/giao-thong-ha-noi"

    def fetch_latest_news(self, max_items: int = 10) -> list[dict]:
        """
        Returns a list of the latest news articles.
        Each item: {"title": str, "summary": str, "url": str}
        Tries RSS first, falls back to web scraping if RSS fails.
        """
        articles = self._fetch_rss(max_items)
        if not articles:
            articles = self._fetch_web(max_items)
        return articles

    def _fetch_rss(self, max_items: int) -> list[dict]:
        try:
            resp = requests.get(self.RSS_URL, timeout=8,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "xml")
            items = soup.find_all("item")[:max_items]
            results = []
            for item in items:
                title = item.find("title")
                desc = item.find("description")
                link = item.find("link")
                results.append({
                    "title": title.get_text(strip=True) if title else "",
                    "summary": BeautifulSoup(
                        desc.get_text(strip=True) if desc else "", "html.parser"
                    ).get_text()[:300],
                    "url": link.get_text(strip=True) if link else "",
                })
            return results
        except Exception as e:
            print(f"[VOVScraper] RSS failed: {e}")
            return []

    def _fetch_web(self, max_items: int) -> list[dict]:
        try:
            resp = requests.get(self.WEB_URL, timeout=8,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # VOV uses different CSS classes across updates — try in priority order
            selectors = [
                "article.story",
                "div.story-item",
                "div.news-item",
                "li.item",
            ]
            articles = []
            for sel in selectors:
                articles = soup.select(sel)
                if articles:
                    break

            results = []
            for art in articles[:max_items]:
                a_tag = art.find("a", href=True)
                title = a_tag.get_text(strip=True) if a_tag else art.get_text(strip=True)[:100]
                p_tag = art.find("p")
                summary = p_tag.get_text(strip=True)[:300] if p_tag else ""
                url = a_tag["href"] if a_tag else ""
                if url and not url.startswith("http"):
                    url = "https://vovgiaothong.vn" + url
                results.append({"title": title, "summary": summary, "url": url})
            return results
        except Exception as e:
            print(f"[VOVScraper] Web scrape failed: {e}")
            return []


# ──────────────────────────────────────────────
#  Gemini Traffic Client
# ──────────────────────────────────────────────

class GeminiTrafficClient:
    """
    Integrates Gemini LLM as a two-way translator:
      Text  →  Picture Fuzzy parameters (P, N, n)   [parse_traffic_text_to_fuzzy]
      Parameters  →  Natural language explanation    [generate_route_explanation]

    API key is read from the GEMINI_API_KEY environment variable (.env file).
    """

    LOCATIONS = [
        "My Dinh", "Cau Giay", "Nguyen Chi Thanh", "Duong Lang",
        "Kim Ma", "La Thanh", "Nga Tu So", "Xa Dan",
        "Truong Chinh", "Dai Co Viet", "HUST",
    ]

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = "gemini-1.5-flash"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self._scraper = VOVTrafficScraper()

    # ── Public helpers ────────────────────────

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    # ── VOV integration ───────────────────────

    def fetch_and_parse_vov(self, max_items: int = 10) -> list[dict]:
        """
        Fetches the latest VOV news and converts each article into fuzzy parameters.
        Returns a list of results (each item includes a 'source_url' key).
        """
        articles = self._scraper.fetch_latest_news(max_items)
        if not articles:
            print("[GeminiClient] No VOV articles retrieved.")
            return []

        results = []
        for art in articles:
            text = f"{art['title']}. {art['summary']}".strip()
            if not text:
                continue
            parsed = self.parse_traffic_text_to_fuzzy(text)
            parsed["source_url"] = art.get("url", "")
            parsed["raw_text"] = text
            results.append(parsed)
        return results

    # ── Chiều xuôi: Text → Fuzzy ──────────────

    def parse_traffic_text_to_fuzzy(self, text: str) -> dict:
        """
        Uses Gemini to translate a traffic report text → fuzzy triple (P, N, n).
        Falls back to rule-based parsing if no API key is set or the API call fails.
        """
        if not self.is_configured():
            return self._mock_parse_traffic_text(text)

        location_list = ", ".join(self.LOCATIONS)
        prompt = f"""
You are an expert in intelligent traffic data analysis.
Translate the following traffic report text into a Picture Fuzzy Number triple (P, N, n):

- P (Positive)  : Degree of clear traffic flow, good movement, fast travel. Value in [0.0, 1.0].
- N (Neutral)   : Degree of uncertainty due to bad weather or unclear information. Value in [0.0, 1.0].
- n (Negative)  : Degree of congestion, traffic jam, should be avoided. Value in [0.0, 1.0].

Mandatory constraint: 0 ≤ P + N + n ≤ 1.0

Identify the location — choose ONLY ONE from the following list (exact spelling):
{location_list}

Return a single JSON object, NO markdown, NO explanation:
{{
  "location": "<location name>",
  "fuzzy": [P, N, n],
  "confidence": <0.0–1.0>
}}

Text: "{text}"
"""
        result = self._call_gemini_json(prompt, timeout=8)
        if result is None:
            return self._mock_parse_traffic_text(text)

        # Normalise fuzzy values
        try:
            p, nv, neg = [float(x) for x in result["fuzzy"]]
            total = p + nv + neg
            if total > 1.0:
                p, nv, neg = p / total, nv / total, neg / total
            result["fuzzy"] = [round(p, 2), round(nv, 2), round(neg, 2)]
        except Exception:
            return self._mock_parse_traffic_text(text)

        return result

    # ── Chiều ngược: Thông số → Text ─────────

    def generate_route_explanation(
        self,
        source: str,
        target: str,
        pfig_route: list[str],
        dijkstra_route: list[str],
        pfig_metrics: dict,
        dijkstra_metrics: dict,
        avoided_bottlenecks: list[dict],
        weather: str,
        time_of_day: str,
    ) -> str:
        """
        Uses Gemini to generate a natural language explanation of the route decision.
        Falls back to mock if no API key is set or the API call fails.
        """
        if not self.is_configured():
            return self._mock_route_explanation(
                source, target, pfig_route, dijkstra_route,
                pfig_metrics, dijkstra_metrics, avoided_bottlenecks,
                weather, time_of_day,
            )

        bottlenecks_str = json.dumps(avoided_bottlenecks, ensure_ascii=False, indent=2)
        pfig_path = " → ".join(pfig_route)
        dijk_path = " → ".join(dijkstra_route)

        prompt = f"""
You are a Traffic Explanation Assistant (Explainable AI).
Task: explain why the system chose the PFIG route over traditional Dijkstra.

━━ TRIP INFORMATION ━━
Origin      : {source}
Destination : {target}
Weather     : {weather}
Time of day : {time_of_day}

━━ PFIG ROUTE (selected) ━━
Path        : {pfig_path}
Distance: {pfig_metrics['distance_km']} km  |  Duration: {pfig_metrics['duration_mins']} min  |  Delay: {pfig_metrics['delay_mins']} min
Fuzzy score : P={pfig_metrics['intensity'][0]}, N={pfig_metrics['intensity'][1]}, n={pfig_metrics['intensity'][2]}

━━ DIJKSTRA ROUTE (shortest path / Google Maps baseline) ━━
Path        : {dijk_path}
Distance: {dijkstra_metrics['distance_km']} km  |  Duration: {dijkstra_metrics['duration_mins']} min  |  Delay: {dijkstra_metrics['delay_mins']} min
Fuzzy score : P={dijkstra_metrics['intensity'][0]}, N={dijkstra_metrics['intensity'][1]}, n={dijkstra_metrics['intensity'][2]}

━━ AVOIDED BOTTLENECKS ━━
{bottlenecks_str}

━━ REPORT REQUIREMENTS ━━
Write in English, natural and professional tone, use bullet points. Include:
1. Summary of benefit: how many minutes saved compared to Dijkstra.
2. Specific analysis of each avoided bottleneck and the reason.
3. Explanation of the fuzzy score (P, N, n) for the selected route.
4. Clarify the role of the LLM (translator) and the modified Dijkstra core (PFIG Core) in the system.
"""

        advice = self._generate_human_advice(
            source, target, pfig_route, pfig_metrics, dijkstra_metrics,
            avoided_bottlenecks, weather, time_of_day,
        )

        url = f"{self.base_url}/{self.model_name}:generateContent?key={self.api_key}"
        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            explanation = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return f"{advice}\n\n---\n\n{explanation}"
        except Exception as e:
            print(f"[GeminiClient] generate_route_explanation error: {e}. Using mock.")
            return self._mock_route_explanation(
                source, target, pfig_route, dijkstra_route,
                pfig_metrics, dijkstra_metrics, avoided_bottlenecks,
                weather, time_of_day,
            )

    # ── Internal: gọi Gemini, parse JSON ─────

    def _call_gemini_json(self, prompt: str, timeout: int = 8) -> dict | None:
        url = f"{self.base_url}/{self.model_name}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Strip markdown fence if the model still adds it
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(raw)
        except Exception as e:
            print(f"[GeminiClient] _call_gemini_json error: {e}")
            return None

    # ── Fallback rule-based ───────────────────

    def _mock_parse_traffic_text(self, text: str) -> dict:
        text_lower = text.lower()
        found_loc = "Nga Tu So"
        for loc in self.LOCATIONS:
            if loc.lower().replace(" ", "") in text_lower.replace(" ", ""):
                found_loc = loc
                break

        if any(k in text_lower for k in ["kẹt", "tắc", "nhích", "ùn ứ", "ách tắc",
                                          "congested", "gridlock", "standstill", "jammed", "blocked"]):
            fuzzy = [0.05, 0.15, 0.75]
        elif any(k in text_lower for k in ["thông thoáng", "vắng", "trơn tru", "lưu thông tốt",
                                            "clear", "free-flowing", "smooth", "light traffic"]):
            fuzzy = [0.80, 0.10, 0.05]
        elif any(k in text_lower for k in ["mưa", "ngập", "trơn", "sương",
                                            "rain", "flood", "wet", "fog", "foggy"]):
            fuzzy = [0.30, 0.50, 0.15]
        elif any(k in text_lower for k in ["chậm", "đông", "chú ý",
                                            "slow", "heavy", "caution", "dense"]):
            fuzzy = [0.20, 0.30, 0.45]
        else:
            fuzzy = [0.40, 0.30, 0.25]

        return {
            "location": found_loc,
            "fuzzy": fuzzy,
            "confidence": 0.75,
            "source": "Rule-Based Fallback (no API key)",
        }

    def _mock_route_explanation(
        self, source, target, pfig_route, dijkstra_route,
        pfig_metrics, dijkstra_metrics, avoided_bottlenecks,
        weather, time_of_day,
    ) -> str:
        time_saved = dijkstra_metrics["duration_mins"] - pfig_metrics["duration_mins"]
        dist_diff = pfig_metrics["distance_km"] - dijkstra_metrics["distance_km"]

        advice = self._generate_human_advice(
            source, target, pfig_route, pfig_metrics, dijkstra_metrics,
            avoided_bottlenecks, weather, time_of_day,
        )

        lines = [
            advice,
            "\n---\n",
            "### PFIG Optimal Route Analysis\n",
            f"Conditions: weather **{weather.upper()}**, time of day **{time_of_day.upper()}**.\n",
        ]

        if time_saved > 0:
            lines.append(
                f"- **Efficiency**: Saves **{time_saved:.1f} minutes** compared to the Dijkstra route "
                f"(though {dist_diff:.2f} km longer)."
            )
        else:
            lines.append("- **Optimal route** coincides with the shortest path but offers higher reliability.")

        if avoided_bottlenecks:
            names = [f"**{b['node']}** (n={b['n']})" for b in avoided_bottlenecks]
            lines.append(f"- **Avoided bottlenecks**: {', '.join(names)}.")

        p, nv, neg = pfig_metrics["intensity"]
        lines.append(
            f"- **Route fuzzy score**: P={p} (clear flow), N={nv} (uncertainty), n={neg} (congestion). "
            f"The high P value indicates favourable traffic conditions."
        )

        lines += [
            "\n### Role of LLM in the System",
            "> - **LLM does NOT plan the route** — the routing core is a Modified Dijkstra on a PFIG graph (NetworkX).",
            "> - **Forward pass (Text→Math)**: LLM translates VOV news articles into fuzzy weights (P, N, n) fed into the graph.",
            "> - **Backward pass (Math→Text)**: LLM translates the mathematical result into a natural language explanation like the one above.",
        ]

        return "\n".join(lines)

    def _generate_human_advice(
        self,
        source: str,
        target: str,
        pfig_route: list[str],
        pfig_metrics: dict,
        dijkstra_metrics: dict,
        avoided_bottlenecks: list[dict],
        weather: str,
        time_of_day: str,
    ) -> str:
        """
        Generates a concise, human-sounding travel recommendation based on
        computed route metrics. Prepended before the full technical explanation.
        """
        p, nv, neg = pfig_metrics["intensity"]
        time_saved = dijkstra_metrics["duration_mins"] - pfig_metrics["duration_mins"]
        duration = pfig_metrics["duration_mins"]
        via_stops = pfig_route[1:-1]  # intermediate nodes only

        # ── Tone: congestion level ──────────────────────────────────────
        if neg >= 0.6:
            congestion_note = (
                "Heavy traffic. Avoid shortcuts. "
            )
        elif neg >= 0.35:
            congestion_note = (
                "Congestion on a few roads "
                "— worth the detour."
            )
        else:
            congestion_note = "Roads are clear."

        # ── Tone: weather ───────────────────────────────────────────────
        weather_lower = weather.lower()
        if any(w in weather_lower for w in ["rain", "wet", "flood", "storm"]):
            weather_note = " It's wet. Leave early."
        elif any(w in weather_lower for w in ["fog", "mist", "haze"]):
            weather_note = " Foggy weather. Drive slowly and cautiously."
        else:
            weather_note = ""

        # ── Tone: time of day ───────────────────────────────────────────
        time_lower = time_of_day.lower()
        if any(t in time_lower for t in ["rush", "peak", "morning", "evening", "pm", "am"]):
            time_note = " Suggesting route below to avoid rush hour congestion."
        else:
            time_note = ""

        # ── Time saving framing ─────────────────────────────────────────
        if time_saved >= 5:
            saving_note = (
                f" Arriving in **{duration:.0f} minutes** — "
                f"roughly **{time_saved:.0f} minutes faster** than going the direct way."
            )
        elif time_saved > 0:
            saving_note = (
                f" Longer route, likely faster. "
                f"in **{duration:.0f} minutes** overall — still quicker than the straight route."
            )
        else:
            saving_note = (
                f" Recommended route matches shortest, "
                f"but more reliable given current conditions."
            )

        # ── Via note ────────────────────────────────────────────────────
        if via_stops:
            via_note = f" Head via {' → '.join(via_stops)}."
        else:
            via_note = ""

        # ── Bottleneck callout ──────────────────────────────────────────
        if avoided_bottlenecks:
            bad_spots = [b["node"] for b in avoided_bottlenecks]
            if len(bad_spots) == 1:
                bn_note = f" Avoid **{bad_spots[0]}** — heavy traffic."
            else:
                listed = ", ".join(f"**{s}**" for s in bad_spots[:-1])
                bn_note = f" Best to avoid {listed} and **{bad_spots[-1]}** — all congested."
        else:
            bn_note = ""

        advice = (
            f"**My recommendation for {source} → {target}:** "
            f"{congestion_note}{weather_note}{time_note}"
            f"{saving_note}{via_note}{bn_note}"
        )

        return f"> 💬 {advice}"