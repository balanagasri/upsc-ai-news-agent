import os
import json
import re
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import smtplib
import html

from datetime import datetime

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ============================================================
# 1. FETCH NEWS
# ============================================================

queries = [
    "India government policy",
    "India economy RBI",
    "Supreme Court India",
    "India environment climate",
    "India science technology",
    "India international relations",
    "India government schemes"
]

articles = []

for query in queries:

    encoded_query = urllib.parse.quote(query)

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:

        with urllib.request.urlopen(
            rss_url,
            timeout=20
        ) as response:

            xml_data = response.read()

        root = ET.fromstring(xml_data)

        for item in root.findall(".//item")[:5]:

            title = item.findtext("title", "")
            link = item.findtext("link", "")
            description = item.findtext("description", "")

            articles.append({
                "title": title,
                "link": link,
                "description": description
            })

    except Exception as e:

        print(
            f"Could not fetch '{query}': {e}"
        )


# ============================================================
# 2. REMOVE DUPLICATES
# ============================================================

unique_articles = {}

for article in articles:

    title = article["title"].strip()

    if title:

        unique_articles[title] = article


articles = list(unique_articles.values())

print(
    f"Collected {len(articles)} unique articles."
)


if not articles:

    raise Exception(
        "No news articles were collected."
    )


# ============================================================
# 3. PREPARE NEWS FOR GEMINI
# ============================================================

news_text = ""

for i, article in enumerate(
    articles[:30],
    1
):

    news_text += (

        f"\nARTICLE {i}\n"

        f"TITLE: "
        f"{article['title']}\n"

        f"DESCRIPTION: "
        f"{article['description']}\n"

        f"SOURCE LINK: "
        f"{article['link']}\n"

        f"--------------------------------------------------\n"
    )


# ============================================================
# 4. GEMINI PROMPT
# ============================================================

prompt = f"""
You are an expert UPSC Civil Services Examination
current-affairs analyst.

Create a concise, accurate daily UPSC current-affairs
briefing from the supplied news articles.

IMPORTANT ACCURACY RULES:

1. Do not invent facts.

2. Do not claim that a government action, Supreme Court
   order, RBI decision, policy, scheme, statistic or
   international event happened unless the supplied
   article supports it.

3. Do not create statistics, dates, laws, schemes,
   organizations or statements that are not supported
   by the supplied material.

4. If an important fact cannot be established from the
   supplied material, write:

   "Requires verification."

5. Do not confuse an article's opinion or criticism with
   an established government decision.

6. Do not present speculation as fact.

7. Keep the briefing useful for UPSC preparation rather
   than general news reading.

8. For every selected topic, use the SOURCE LINK supplied
   in the article data.

9. The SOURCE URL must be copied EXACTLY from the supplied
   SOURCE LINK.

10. Do NOT modify, shorten, rewrite, invent, or replace
    the SOURCE URL.

11. Never create a fake URL.

PRIORITIZE:

- Indian Polity
- Constitution
- Governance
- Judiciary
- Government schemes
- Economy
- Banking and RBI
- Environment
- Climate change
- Biodiversity
- Agriculture
- Science and Technology
- International Relations
- Internal Security
- Social Issues
- Important reports and indices

IGNORE:

- Sports
- Entertainment
- Celebrity news
- Gossip
- Advertisements
- Trivial local news
- Sensational stories with little UPSC relevance

SELECT:

Select approximately 5-8 genuinely important UPSC topics.

For every selected topic use EXACTLY this structure:

### TOPIC: <title>

**Category:** <category>

**UPSC Relevance Score:** <score>/100

**What Happened:**
Explain in 2-4 concise sentences.

**Why It Matters for UPSC:**
Explain in 2-4 concise sentences.

**GS Paper:**
GS-1, GS-2, GS-3, GS-4 or Essay.

**Prelims Facts:**
1. Useful fact.
2. Useful fact.
3. Useful fact.

**Mains Angle:**
One analytical UPSC-style Mains question.

**Source:**
Article title - source name.

**Source URL:**
EXACT SOURCE LINK copied from the supplied article data.

IMPORTANT:

- The Source URL must be the exact URL from one of the supplied
  SOURCE LINK fields.
- Do not generate a new URL.
- Do not change the URL.
- Do not use a homepage URL instead.
- Do not use a shortened URL.
- Do not use Markdown links.
- Output the complete URL as plain text.

Do NOT add a fourth numbered item under Prelims Facts.

At the end provide:

### TOP 5 QUICK REVISION POINTS

1. ...
2. ...
3. ...
4. ...
5. ...

Then provide:

### PRELIMS MCQs

Create exactly 3 MCQs.

Each MCQ must contain:

#### MCQ 1

Question

A) ...

B) ...

C) ...

D) ...

**Correct Answer:** X

**Explanation:** One concise explanation.

Then MCQ 2 and MCQ 3.

Finally provide:

### MAINS PRACTICE QUESTION

One UPSC-style analytical question of approximately
150-250 words.

NEWS ARTICLES:

{news_text}
"""


# ============================================================
# 5. CALL GEMINI
# ============================================================

api_key = os.environ["GEMINI_API_KEY"]

gemini_url = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.5-flash:generateContent"
)

request_body = {

    "contents": [

        {
            "parts": [

                {
                    "text": prompt
                }

            ]
        }

    ]

}

request = urllib.request.Request(

    gemini_url,

    data=json.dumps(
        request_body
    ).encode("utf-8"),

    headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    },

    method="POST"
)

try:

    with urllib.request.urlopen(
        request,
        timeout=120
    ) as response:

        result = json.loads(
            response.read().decode("utf-8")
        )

except urllib.error.HTTPError as e:

    print(
        f"Gemini API returned HTTP {e.code}"
    )

    print(
        e.read().decode("utf-8")
    )

    raise


# ============================================================
# 6. EXTRACT GEMINI RESPONSE
# ============================================================

try:

    briefing = (
        result["candidates"][0]
        ["content"]["parts"][0]["text"]
    )

except Exception:

    print(
        "Unexpected Gemini response:"
    )

    print(
        json.dumps(
            result,
            indent=2
        )
    )

    raise


print(
    "\n===================================="
)

print(
    "UPSC DAILY CURRENT AFFAIRS"
)

print(
    "====================================\n"
)

print(briefing)


# ============================================================
# 7. HTML FORMATTING HELPERS
# ============================================================

today = datetime.now().strftime(
    "%d %B %Y"
)


def clean_text(text):

    """
    Convert basic Markdown into safe HTML.
    """

    text = text.strip()

    # Remove leading markdown bullets
    text = re.sub(
        r"^\s*[-*]\s+",
        "",
        text
    )

    # Escape HTML
    text = html.escape(
        text
    )

    # Bold
    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"<strong>\1</strong>",
        text
    )

    # Italic
    text = re.sub(
        r"(?<!\*)\*(?!\s)(.*?)(?<!\s)\*",
        r"<em>\1</em>",
        text
    )

    # Remove remaining markdown stars
    text = text.replace(
        "*",
        ""
    )

    return text


def extract_link(text):

    """
    Extract a URL from Markdown or plain text.
    """

    match = re.search(
        r"https?://[^\s)\]>]+",
        text
    )

    if match:

        return match.group(0).rstrip(
            ".,;:!?\"'"
        )

    return ""


def remove_markdown_link(text):

    """
    Turn:

    [Source](URL)

    into:

    Source
    """

    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text
    )

    return text


# ============================================================
# 8. BUILD BEAUTIFUL HTML
# ============================================================

def build_html(briefing):

    lines = briefing.replace(
        "\r",
        ""
    ).split("\n")

    output = []

    current_topic_open = False
    current_special_open = False
    in_numbered_list = False

    current_source_name = ""
    current_source_url = ""

    def close_numbered_list():

        nonlocal in_numbered_list

        if in_numbered_list:

            output.append(
                "</ol>"
            )

            in_numbered_list = False


    def close_topic():

        nonlocal current_topic_open

        close_numbered_list()

        if current_topic_open:

            output.append(
                "</div>"
            )

            current_topic_open = False


    def close_special():

        nonlocal current_special_open

        close_numbered_list()

        if current_special_open:

            output.append(
                "</div>"
            )

            current_special_open = False


    def add_source_box():

        nonlocal current_source_name
        nonlocal current_source_url

        if not current_source_name and not current_source_url:
            return

        clean_source = remove_markdown_link(
            current_source_name
        )

        clean_source = re.sub(
            r"https?://[^\s]+",
            "",
            clean_source
        ).strip()

        if current_source_url:

            output.append(
                f"""
                <div class="source-box">

                    <div class="source-label">
                        🔗 Source
                    </div>

                    <div class="source-name">
                        {clean_text(clean_source)}
                    </div>

                    <a
                        class="source-button"
                        href="{html.escape(current_source_url, quote=True)}"
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        Read Source →
                    </a>

                </div>
                """
            )

        else:

            output.append(
                f"""
                <div class="source-box">

                    <div class="source-label">
                        🔗 Source
                    </div>

                    <div class="source-name">
                        {clean_text(clean_source)}
                    </div>

                </div>
                """
            )

        current_source_name = ""
        current_source_url = ""


    for raw_line in lines:

        line = raw_line.strip()


        # ----------------------------------------------------
        # EMPTY LINE
        # ----------------------------------------------------

        if not line:

            close_numbered_list()

            continue


        # ----------------------------------------------------
        # TOPIC
        # ----------------------------------------------------

        topic_match = re.match(
            r"^###\s*TOPIC\s*:?\s*(.*)$",
            line,
            re.IGNORECASE
        )

        if topic_match:

            add_source_box()

            close_numbered_list()
            close_special()
            close_topic()

            title = topic_match.group(1).strip()

            output.append(
                f"""
                <div class="topic-card">

                    <div class="topic-title">
                        {clean_text(title)}
                    </div>

                    <div class="topic-body">
                """
            )

            current_topic_open = True

            continue


        # ----------------------------------------------------
        # SPECIAL SECTION: QUICK REVISION
        # ----------------------------------------------------

        if re.match(
            r"^###\s*TOP 5 QUICK REVISION POINTS",
            line,
            re.IGNORECASE
        ):

            add_source_box()

            close_numbered_list()
            close_topic()
            close_special()

            output.append(
                """
                <div class="special-card revision-card">

                    <div class="special-title">
                        ⚡ Top 5 Quick Revision Points
                    </div>

                    <div class="special-body">
                """
            )

            current_special_open = True

            continue


        # ----------------------------------------------------
        # SPECIAL SECTION: MCQs
        # ----------------------------------------------------

        if re.match(
            r"^###\s*PRELIMS MCQS",
            line,
            re.IGNORECASE
        ):

            add_source_box()

            close_numbered_list()
            close_topic()
            close_special()

            output.append(
                """
                <div class="special-card mcq-card">

                    <div class="special-title">
                        ❓ Prelims MCQs
                    </div>

                    <div class="special-body">
                """
            )

            current_special_open = True

            continue


        # ----------------------------------------------------
        # SPECIAL SECTION: MAINS
        # ----------------------------------------------------

        if re.match(
            r"^###\s*MAINS PRACTICE QUESTION",
            line,
            re.IGNORECASE
        ):

            add_source_box()

            close_numbered_list()
            close_topic()
            close_special()

            output.append(
                """
                <div class="special-card mains-card">

                    <div class="special-title">
                        ✍️ Mains Practice Question
                    </div>

                    <div class="special-body">
                """
            )

            current_special_open = True

            continue


        # ----------------------------------------------------
        # MCQ NUMBER
        # ----------------------------------------------------

        mcq_match = re.match(
            r"^####\s*(MCQ\s*\d+)",
            line,
            re.IGNORECASE
        )

        if mcq_match:

            close_numbered_list()

            title = mcq_match.group(1)

            output.append(
                f"""
                <div class="mcq-title">
                    {clean_text(title)}
                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # SECTION HEADINGS
        # ----------------------------------------------------

        heading_match = re.match(
            r"^####\s+(.+)$",
            line
        )

        if heading_match:

            close_numbered_list()

            heading = heading_match.group(1).strip()

            heading = re.sub(
                r"^\d+\.\s*",
                "",
                heading
            )

            heading_lower = heading.lower()

            if "what happened" in heading_lower:

                icon = "📰"

            elif "why it matters" in heading_lower:

                icon = "🎯"

            elif "prelims facts" in heading_lower:

                icon = "📌"

            elif "mains angle" in heading_lower:

                icon = "✍️"

            elif "source" in heading_lower:

                icon = "🔗"

            else:

                icon = "▸"

            output.append(
                f"""
                <div class="section-heading">
                    {icon} {clean_text(heading)}
                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # CATEGORY
        # ----------------------------------------------------

        category_match = re.search(
            r"\*\*Category:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if category_match:

            close_numbered_list()

            value = category_match.group(1).strip()

            output.append(
                f"""
                <span class="badge category">
                    🏷️ {clean_text(value)}
                </span>
                """
            )

            continue


        # ----------------------------------------------------
        # RELEVANCE SCORE
        # ----------------------------------------------------

        relevance_match = re.search(
            r"\*\*UPSC Relevance Score:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if relevance_match:

            close_numbered_list()

            value = relevance_match.group(1).strip()

            output.append(
                f"""
                <span class="badge relevance">
                    🎯 UPSC Relevance: {clean_text(value)}
                </span>
                """
            )

            continue


        # ----------------------------------------------------
        # GS PAPER
        # ----------------------------------------------------

        gs_match = re.search(
            r"\*\*GS Paper:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if gs_match:

            close_numbered_list()

            value = gs_match.group(1).strip()

            output.append(
                f"""
                <span class="badge gs">
                    📚 {clean_text(value)}
                </span>
                """
            )

            continue


        # ----------------------------------------------------
        # SOURCE URL
        # ----------------------------------------------------

        source_url_match = re.search(
            r"\*\*Source URL:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if source_url_match:

            close_numbered_list()

            url_text = source_url_match.group(1).strip()

            url = extract_link(
                url_text
            )

            if url:

                current_source_url = url

            continue


        # ----------------------------------------------------
        # SOURCE
        # ----------------------------------------------------

        source_match = re.search(
            r"\*\*Source:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if source_match:

            close_numbered_list()

            current_source_name = source_match.group(1).strip()

            # Sometimes Gemini may include the URL on the
            # same Source line.
            same_line_url = extract_link(
                current_source_name
            )

            if same_line_url:

                current_source_url = same_line_url

            # Don't immediately create the box.
            # We wait for Source URL.
            continue


        # ----------------------------------------------------
        # OLD SOURCE LINK FORMAT
        # ----------------------------------------------------

        if re.search(
            r"\*\*Source Link:\*\*",
            line,
            re.IGNORECASE
        ):

            close_numbered_list()

            old_url = extract_link(
                line
            )

            if old_url:

                current_source_url = old_url

            continue


        # ----------------------------------------------------
        # CORRECT ANSWER
        # ----------------------------------------------------

        answer_match = re.search(
            r"\*\*Correct Answer:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if answer_match:

            close_numbered_list()

            value = answer_match.group(1).strip()

            output.append(
                f"""
                <div class="answer-box">

                    <strong>
                        ✅ Correct Answer:
                    </strong>

                    {clean_text(value)}

                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # EXPLANATION
        # ----------------------------------------------------

        explanation_match = re.search(
            r"\*\*Explanation:\*\*\s*(.*)",
            line,
            re.IGNORECASE
        )

        if explanation_match:

            close_numbered_list()

            value = explanation_match.group(1).strip()

            output.append(
                f"""
                <div class="explanation">

                    <strong>Explanation:</strong>
                    {clean_text(value)}

                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # MCQ OPTIONS
        # ----------------------------------------------------

        option_match = re.match(
            r"^([A-D])\)\s*(.*)",
            line
        )

        if option_match:

            close_numbered_list()

            letter = option_match.group(1)

            value = option_match.group(2)

            output.append(
                f"""
                <div class="option">

                    <span class="option-letter">
                        {html.escape(letter)}
                    </span>

                    <span>
                        {clean_text(value)}
                    </span>

                </div>
                """
            )

            continue


        # ----------------------------------------------------
        # NUMBERED LIST
        # ----------------------------------------------------

        numbered_match = re.match(
            r"^(\d+)\.\s+(.*)",
            line
        )

        if numbered_match:

            number = numbered_match.group(1)

            value = numbered_match.group(2)

            # If Gemini accidentally produces
            # "4. Mains Angle", don't treat it as a fact.

            if re.match(
                r"^(mains angle|source|source url|what happened|why it matters)",
                value,
                re.IGNORECASE
            ):

                close_numbered_list()

                heading = value

                output.append(
                    f"""
                    <div class="section-heading">
                        ✍️ {clean_text(heading)}
                    </div>
                    """
                )

                continue


            if not in_numbered_list:

                output.append(
                    "<ol class=\"facts-list\">"
                )

                in_numbered_list = True


            output.append(
                f"""
                <li>
                    {clean_text(value)}
                </li>
                """
            )

            continue


        # ----------------------------------------------------
        # HORIZONTAL RULE
        # ----------------------------------------------------

        if line.startswith("---"):

            close_numbered_list()

            output.append(
                "<hr>"
            )

            continue


        # ----------------------------------------------------
        # NORMAL TEXT
        # ----------------------------------------------------

        close_numbered_list()

        cleaned = remove_markdown_link(
            line
        )

        cleaned = cleaned.strip()

        if not cleaned:

            continue

        output.append(
            f"""
            <p>
                {clean_text(cleaned)}
            </p>
            """
        )


    # --------------------------------------------------------
    # FINAL CLEANUP
    # --------------------------------------------------------

    close_numbered_list()

    add_source_box()

    close_topic()

    close_special()

    return "\n".join(
        output
    )


# ============================================================
# 9. GENERATE EMAIL CONTENT
# ============================================================

email_content = build_html(
    briefing
)


# ============================================================
# 10. BEAUTIFUL EMAIL
# ============================================================

html_email = f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
    UPSC Daily Current Affairs
</title>

<style>

/* ==========================================================
   GENERAL
   ========================================================== */

body {{

    margin: 0;

    padding: 0;

    background: #eef2f7;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    color: #1e293b;

    line-height: 1.6;
}}


/* ==========================================================
   MAIN CONTAINER
   ========================================================== */

.container {{

    width: 100%;

    max-width: 760px;

    margin: 30px auto;

    background: #ffffff;

    border-radius: 16px;

    overflow: hidden;

    box-shadow:
        0 6px 25px
        rgba(15, 23, 42, 0.10);
}}


/* ==========================================================
   HEADER
   ========================================================== */

.header {{

    background:
        linear-gradient(
            135deg,
            #172554,
            #1e3a8a
        );

    color: #ffffff;

    padding: 36px 25px;

    text-align: center;
}}

.header h1 {{

    margin: 0;

    font-size: 28px;

    line-height: 1.3;
}}

.header-subtitle {{

    margin-top: 10px;

    font-size: 15px;

    opacity: 0.90;
}}

.header-date {{

    margin-top: 14px;

    display: inline-block;

    padding: 6px 12px;

    border-radius: 20px;

    background:
        rgba(255,255,255,0.12);

    font-size: 13px;
}}


/* ==========================================================
   CONTENT
   ========================================================== */

.content {{

    padding: 28px;
}}


/* ==========================================================
   TOPIC CARD
   ========================================================== */

.topic-card {{

    margin-bottom: 24px;

    border:
        1px solid #e2e8f0;

    border-radius: 14px;

    overflow: hidden;

    background: #ffffff;

    box-shadow:
        0 3px 12px
        rgba(15, 23, 42, 0.05);
}}

.topic-title {{

    padding: 20px 22px;

    background:
        #f8fafc;

    border-bottom:
        1px solid #e2e8f0;

    color: #172554;

    font-size: 20px;

    font-weight: 700;

    line-height: 1.4;
}}

.topic-body {{

    padding: 20px 22px;
}}


/* ==========================================================
   BADGES
   ========================================================== */

.badge {{

    display: inline-block;

    margin:
        0 7px 12px 0;

    padding:
        6px 11px;

    border-radius: 20px;

    font-size: 12px;

    font-weight: 700;
}}

.category {{

    background: #e0f2fe;

    color: #075985;
}}

.relevance {{

    background: #fef3c7;

    color: #92400e;
}}

.gs {{

    background: #ede9fe;

    color: #5b21b6;
}}


/* ==========================================================
   SECTION HEADINGS
   ========================================================== */

.section-heading {{

    margin-top: 20px;

    margin-bottom: 8px;

    color: #334155;

    font-size: 13px;

    font-weight: 800;

    letter-spacing: 0.5px;

    text-transform: uppercase;
}}


/* ==========================================================
   PARAGRAPHS
   ========================================================== */

p {{

    margin:
        7px 0 13px;

    font-size: 15px;

    line-height: 1.75;

    color: #334155;
}}

strong {{

    color: #0f172a;
}}


/* ==========================================================
   FACTS
   ========================================================== */

.facts-list {{

    margin:
        8px 0 15px;

    padding-left: 26px;
}}

.facts-list li {{

    margin-bottom: 10px;

    padding-left: 4px;

    line-height: 1.65;

    font-size: 14px;
}}


/* ==========================================================
   SOURCE
   ========================================================== */

.source-box {{

    margin-top: 20px;

    padding: 16px;

    border:
        1px solid #dbeafe;

    border-radius: 10px;

    background: #f8fafc;
}}

.source-label {{

    color: #334155;

    font-size: 12px;

    font-weight: 800;

    text-transform: uppercase;
}}

.source-name {{

    margin:
        5px 0 12px;

    color: #475569;

    font-size: 13px;

    line-height: 1.5;
}}

.source-button {{

    display: inline-block;

    padding:
        9px 15px;

    background: #1d4ed8;

    color: #ffffff !important;

    border-radius: 7px;

    text-decoration: none;

    font-size: 12px;

    font-weight: 700;
}}

.source-button:hover {{

    text-decoration: none;
}}


/* ==========================================================
   ARTICLE TITLE
   ========================================================== */

.article-title {{

    margin-top: 12px;

    color: #64748b;

    font-size: 12px;
}}


/* ==========================================================
   MCQ OPTIONS
   ========================================================== */

.option {{

    display: flex;

    align-items: flex-start;

    gap: 10px;

    margin:
        7px 0;

    padding:
        10px 12px;

    border:
        1px solid #e2e8f0;

    border-radius: 8px;

    background: #f8fafc;

    font-size: 14px;
}}

.option-letter {{

    flex-shrink: 0;

    width: 24px;

    height: 24px;

    display: flex;

    align-items: center;

    justify-content: center;

    border-radius: 50%;

    background: #e2e8f0;

    color: #334155;

    font-weight: 800;

    font-size: 12px;
}}


/* ==========================================================
   MCQ TITLE
   ========================================================== */

.mcq-title {{

    margin-top: 22px;

    margin-bottom: 10px;

    color: #4c1d95;

    font-size: 16px;

    font-weight: 800;
}}


/* ==========================================================
   ANSWER
   ========================================================== */

.answer-box {{

    margin-top: 13px;

    padding:
        12px 14px;

    background: #ecfdf5;

    border-left:
        4px solid #10b981;

    border-radius: 7px;

    color: #065f46;

    font-size: 14px;
}}


/* ==========================================================
   EXPLANATION
   ========================================================== */

.explanation {{

    margin-top: 8px;

    padding: 10px 12px;

    background: #f8fafc;

    border-radius: 7px;

    color: #475569;

    font-size: 13px;

    line-height: 1.6;
}}


/* ==========================================================
   SPECIAL CARDS
   ========================================================== */

.special-card {{

    margin-top: 28px;

    margin-bottom: 24px;

    padding: 22px;

    border-radius: 14px;
}}

.special-title {{

    margin-bottom: 18px;

    font-size: 20px;

    font-weight: 800;
}}

.special-body {{

    font-size: 14px;
}}


/* ==========================================================
   REVISION
   ========================================================== */

.revision-card {{

    background: #eff6ff;

    border:
        1px solid #bfdbfe;
}}

.revision-card .special-title {{

    color: #1e3a8a;
}}


/* ==========================================================
   MCQ CARD
   ========================================================== */

.mcq-card {{

    background: #faf5ff;

    border:
        1px solid #ddd6fe;
}}

.mcq-card .special-title {{

    color: #5b21b6;
}}


/* ==========================================================
   MAINS CARD
   ========================================================== */

.mains-card {{

    background: #fff7ed;

    border:
        1px solid #fed7aa;
}}

.mains-card .special-title {{

    color: #9a3412;
}}


/* ==========================================================
   DIVIDER
   ========================================================== */

hr {{

    border: 0;

    border-top:
        1px solid #e2e8f0;

    margin:
        22px 0;
}}


/* ==========================================================
   FOOTER
   ========================================================== */

.footer {{

    padding:
        22px 25px;

    background: #f8fafc;

    border-top:
        1px solid #e2e8f0;

    text-align: center;

    color: #64748b;

    font-size: 12px;

    line-height: 1.7;
}}

.footer strong {{

    color: #334155;
}}


/* ==========================================================
   MOBILE
   ========================================================== */

@media only screen and (max-width: 600px) {{

    body {{

        background: #ffffff;
    }}

    .container {{

        margin: 0;

        border-radius: 0;

        box-shadow: none;
    }}

    .header {{

        padding:
            28px 18px;
    }}

    .header h1 {{

        font-size: 23px;
    }}

    .content {{

        padding: 16px;
    }}

    .topic-title {{

        padding:
            17px;

        font-size: 18px;
    }}

    .topic-body {{

        padding:
            17px;
    }}

    .special-card {{

        padding:
            17px;
    }}

    p {{

        font-size: 14px;
    }}

}}

</style>

</head>


<body>


<div class="container">


    <!-- HEADER -->

    <div class="header">

        <h1>
            🇮🇳 UPSC Daily Current Affairs
        </h1>

        <div class="header-subtitle">

            AI-powered Civil Services Briefing

        </div>

        <div class="header-date">

            {today}

        </div>

    </div>


    <!-- CONTENT -->

    <div class="content">

        {email_content}

    </div>


    <!-- FOOTER -->

    <div class="footer">

        <strong>
            UPSC AI News Agent
        </strong>

        <br>

        Generated automatically from current news.

        <br><br>

        ⚠️ Always verify important facts with
        authoritative sources before using them
        in an examination.

    </div>


</div>


</body>

</html>
"""


# ============================================================
# 11. SEND EMAIL
# ============================================================

sender = os.environ[
    "GMAIL_USERNAME"
]

app_password = os.environ[
    "GMAIL_APP_PASSWORD"
]

recipient = sender


message = MIMEMultipart(
    "alternative"
)

message["Subject"] = (
    "UPSC Daily Current Affairs - AI Briefing"
)

message["From"] = sender

message["To"] = recipient


# Plain-text fallback

message.attach(

    MIMEText(

        briefing,

        "plain",

        "utf-8"

    )
)


# HTML email

message.attach(

    MIMEText(

        html_email,

        "html",

        "utf-8"

    )
)


print(
    "\nSending email..."
)


with smtplib.SMTP(
    "smtp.gmail.com",
    587
) as server:

    server.starttls()

    server.login(
        sender,
        app_password
    )

    server.sendmail(
        sender,
        recipient,
        message.as_string()
    )


print(
    "\n===================================="
)

print(
    "EMAIL SENT SUCCESSFULLY"
)

print(
    "===================================="
)
