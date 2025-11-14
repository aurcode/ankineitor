import streamlit as st
import pandas as pd
import yaml
from pathlib import Path
from loguru import logger

# --- Default Anki Configs (from your example) ---
# This is the "basic" setup
DEFAULT_MODEL_TEMPLATES_YAML = """
main:
  - name: "Card 1"
    qfmt: "{{Front}}<br>{{Image}}"
    afmt: "{{FrontSide}}<hr id=answer>{{Back}}<br><br>{{Example}}{{Audio}}<br><br><i>{{Notes}}</i>"
css: |
  .card {
    font-family: arial;
    font-size: 20px;
    text-align: center;
    color: black;
    background-color: white;
  }
"""

DEFAULT_TAG_RULES_YAML = """
- static_tags:
    - "@AURCODE"
    - "PipelineDeck"
- prefix: "Category"
  # column: "categories" # Matches the CSV column
  split_by: ","
"""

# --- NEW: Full Configuration for the "Chinese Pipeline" Button ---
# This dictionary contains all the settings for your specific CSV
CHINESE_PIPELINE_SETUP = {
    "model_id": 20251110,  # New custom ID for this model
    "model_name": "Chinese Pipeline Model (Full)",
    "deck_id": 20251111,
    "note_type": "Chinese (Pipeline)",
    # 1. Anki Model Fields: All the fields in the Anki note
    "model_fields": [
        {"name": "Word"},  # Front
        {"name": "Pinyin"},
        {"name": "English Meaning"},
        {"name": "Spanish Meaning"},
        {"name": "Audio"},
        {"name": "Example 1"},
        {"name": "Example 2"},
        {"name": "Example 3"},
        {"name": "Translation (Extras)"},
        {"name": "Categories"},
        {"name": "Timestamp"},
    ],
    # 2. CSV Column Mapping: Connects CSV columns to Anki fields (in order)
    "model_builder": [
        {"csv_column": "word"},
        {"csv_column": "pinyin"},
        {"csv_column": "meaning_english"},
        {"csv_column": "meaning_spanish"},
        {"csv_column": "audio"},
        {"csv_column": "sentence_1"},
        {"csv_column": "sentence_2"},
        {"csv_column": "sentence_3"},
        {"csv_column": "translation"},
        {"csv_column": "categories"},
        {"csv_column": "timestamp"},
    ],
    # 3. Media Fields: Tells the generator which columns are files
    "media_fields": [
        {"column_name": "audio", "media_type": "audio"},
    ],
    # 4. "Beautiful Template" (YAML for Templates + CSS)
    "model_templates_yaml": """
main:
  - name: "Card 1 (Word -> All)"
    qfmt: |
        <div class="header">What are the <span class="question-sub-text">meanings</span>?</div>
        <br>
        <div id="char_word" class="char-card">{{Word}}</div>
    afmt: |
        <!--
        BACK TEMPLATE
        Shows all the new fields, with toggles and dictionary links updated.
        -->

        <!-- Show the Front Side (Question) -->
        {{FrontSide}}

        <hr>

        <!-- Show the Answers -->
        <div id="char_pinyin" class="pinyin">{{Pinyin}}</div>

        <!-- Meanings Section -->
        <div class="meanings-container">
        <div id="char_english_meaning" class="meaning-card english-meaning">
        {{English Meaning}}
        </div>
        <div id="char_spanish_meaning" class="meaning-card spanish-meaning">
        {{Spanish Meaning}}
        </div>
        </div>

        <!-- Examples Section (Only shows if fields are not empty) -->
        <div class="examples-container">
        {{#Example 1}}
        <div class="example-group">
        <div class="example-sentence">{{Example 1}}</div>
        </div>
        {{/Example 1}}
        {{#Example 2}}
        <div class="example-group">
        <div class="example-sentence">{{Example 2}}</div>
        </div>
        {{/Example 2}}
        {{#Example 3}}
        <div class="example-group">
        <div class="example-sentence">{{Example 3}}</div>
        </div>
        {{/Example 3}}

        {{#Translation (Extras)}}
        <div id="char_extras" class="extras-group">
        <div class="extras-header">Translations / Notes</div>
        <div class="extras-content">{{Translation (Extras)}}</div>
        </div>
        {{/Translation (Extras)}}
        </div>

        <!-- Audio -->
        <div id="char_audio">{{Audio}}</div>

        <!-- Controls: Toggles & Dictionary Button -->
        <div class="controls-container">
        <a href="#" class="toggle-button" onclick="openToggleNav(); return false;">Toggle Options ⚙️</a>
        <a href="#" class="toggle-button" onclick="openNav(); return false;">Dictionaries 📖</a>
        </div>

        <!-- NEW Toggle Options Sidebar (Left) -->
        <div id="myToggleSidebar" class="more-info-sidebar left-sidebar">
            <a href="javascript:void(0)" class="closebtn" onclick="closeToggleNav()">&times;</a>
            <a href="#" class="toggle-button" onclick="toggleField('pinyin'); return false;">Toggle Pinyin</a>
            <a href="#" class="toggle-button" onclick="toggleField('english_meaning'); return false;">Toggle English</a>
            <a href="#" class="toggle-button" onclick="toggleField('spanish_meaning'); return false;">Toggle Spanish</a>
            <a href="#" class="toggle-button" onclick="toggleField('extras'); return false;">Toggle Notes</a>
        </div>

        <!-- More Info Sidebar (for Dictionaries) - Updated to use {{Word}} -->
        <div id="myMoreInfoSidebar" class="more-info-sidebar">
        <a href="javascript:void(0)" class="closebtn" onclick="closeNav()">&times;</a>
        <!-- Dictionary Links Updated to use {{Word}} -->
        <a href="plecoapi://x-callback-url/df?hw={{Word}}">Pleco 🔵</a>
        <a href="http://dict.youdao.com/search?q={{Word}}">Youdao 🟢</a>
        <a href="https://hanzicraft.com/character/{{Word}}">HanziCraft 🟡</a>
        <a href="https://characterpop.com/characters/{{Word}}">CharacterPop ⚪</a>
        <a href="http://rtega.be/chmn/index.php?c={{Word}}">Rtega 🟣</a>
        <a href="https://tatoeba.org/en/sentences/search?from=cmn&query={{Word}}&to=">Tatoeba 🟤</a>
        </div>

        <!-- Scripts (anki-persistence and the display logic) -->
        <script>
        // v1.0.0 - https://github.com/SimonLammer/anki-persistence/
        if(void 0===window.Persistence){var e="[github.com/SimonLammer/anki-persistence/](https://github.com/SimonLammer/anki-persistence/)",t="_default";if(window.Persistence_localStorage=function(){var i=!1;try{null!==window.localStorage&&"object"==typeof window.localStorage&&(i=!0,this.clear=function(){for(var t=0;t<localStorage.length;t++){var i=localStorage.key(t);0==i.indexOf(e)&&(localStorage.removeItem(i),t--)}},this.setItem=function(i,n){void 0==n&&(n=i,i=t),localStorage.setItem(e+i,JSON.stringify(n))},this.getItem=function(i){return void 0==i&&(i=t),JSON.parse(localStorage.getItem(e+i))},this.removeItem=function(i){void 0==i&&(i=t),localStorage.removeItem(e+i)})}catch(n){}this.isAvailable=function(){return i}},window.Persistence_sessionStorage=function(){var i=!1;try{"object"==typeof window.sessionStorage&&(i=!0,this.clear=function(){for(var t=0;t<sessionStorage.length;t++){var i=sessionStorage.key(t);0==i.indexOf(e)&&(sessionStorage.removeItem(i),t--)}},this.setItem=function(i,n){void 0==n&&(n=i,i=t),sessionStorage.setItem(e+i,JSON.stringify(n))},this.getItem=function(i){return void 0==i&&(i=t),JSON.parse(sessionStorage.getItem(e+i))},this.removeItem=function(i){void 0==i&&(i=t),sessionStorage.removeItem(e+i)})}catch(n){}this.isAvailable=function(){return i}},window.Persistence_windowKey=function(i){var n=window[i],o=!1;"object"==typeof n&&(o=!0,this.clear=function(){n[e]={}},this.setItem=function(i,o){void 0==o&&(o=i,i=t),n[e][i]=o},this.getItem=function(i){return void 0==i&&(i=t),void 0==n[e][i]?null:n[e][i]},this.removeItem=function(i){void 0==i&&(i=t),delete n[e][i]},void 0==n[e]&&this.clear()),this.isAvailable=function(){return o}},window.Persistence=new Persistence_sessionStorage,navigator.userAgent.indexOf("Mobile")>0&&(window.Persistence=new Persistence_localStorage,Persistence.isAvailable()||(window.Persistence=new Persistence_sessionStorage)),Persistence.isAvailable()||(window.Persistence=new Persistence_windowKey("py")),!Persistence.isAvailable()){var i=window.location.toString().indexOf("title"),n=window.location.toString().indexOf("main",i);i>0&&n>0&&n-i<10&&(window.Persistence=new Persistence_windowKey("qt"))}}
        </script>
        <script>
        // --- Sidebar Functions ---
        function openNav() {
        document.getElementById("myMoreInfoSidebar").style.width = "250px";
        }

        function closeNav() {
        document.getElementById("myMoreInfoSidebar").style.width = "0";
        }

        // NEW Toggle Sidebar Functions
        function openToggleNav() {
        document.getElementById("myToggleSidebar").style.width = "250px";
        }

        function closeToggleNav() {
        document.getElementById("myToggleSidebar").style.width = "0";
        }

        // --- Field Toggling Functions ---
        // UPDATED: Now includes extras
        var switchIdList = ["text-pinyin", "text-english_meaning", "text-spanish_meaning", "text-extras"];

        function toggleField(field) {
        var persistenceId = "backtext-" + field; // e.g., "backtext-pinyin"
        var elementId = "char_" + field;      // e.g., "char_pinyin"
        var el = document.getElementById(elementId);
        if (!el) return;

        // Check current state (from persistence or style)
        var currentState = Persistence.getItem(persistenceId);
        var isVisible = (currentState === null) ? (el.style.display !== "none") : (currentState === "true");

        // Toggle state
        var newState = !isVisible;
        el.style.display = newState ? "" : "none";
        Persistence.setItem(persistenceId, newState.toString());
        }

        function initSwitchPrefs() {
        for (var _id of switchIdList) {
        var divId = _id.replace("text-", "char_"); // e.g., "char_pinyin"
        var persistenceId = "back" + _id;         // e.g., "backtext-pinyin"
        var el = document.getElementById(divId);
        if (!el) continue;

        var savedState = Persistence.getItem(persistenceId);
        if (savedState == "false") {
        el.style.display = "none";
        } else if (savedState == "true") {
        el.style.display = ""; // Ensure it's visible
        }
        // If 'null', do nothing, respect default CSS
        }
        }

        // --- Utility Functions ---
        function isInWebView() {
        var UA = navigator.userAgent;
        if (/iPhone|iPod|iPad/.test(UA)) {
        if (/(iPhone|iPod|iPad).*AppleWebKit(?!.*Safari)/i.test(UA)) {
        return true;
        }
        }
        if (window.location.href.includes("ankiuser.net")) {
        return true;
        }
        return false;
        }

        // --- Run on Load ---
        if (Persistence.isAvailable()) {
        if (window.ankiPlatform == "desktop" || isInWebView()) {
        initSwitchPrefs();
        } else {
        window.addEventListener("load", initSwitchPrefs, false);
        }
        }
        </script>
css: |
        /* STYLING (CSS)
        Added styles for new English/Spanish meanings and Example fields.
        */
        :root {
            --tone-1: #f44336;
            --tone-2: #ff9800;
            --tone-3: #4caf50;
            --tone-4: #2196f3;
            --tone-5: #607d8b;
            --brand-bg1: rgb(255, 117, 195);
            --brand-bg2: rgb(157, 119, 255);
            --brand-bg-gradient: linear-gradient(to bottom,
                    var(--brand-bg1),
                    var(--brand-bg2));
            --thumb-highlight-color: rgba(255, 255, 254, 0.2);
            --space-xxs: .25rem;
            --space-xs: .5rem;
            --space-sm: 1rem;
            --space-md: 1.5rem;
            --space-lg: 2rem;
            --space-xl: 3rem;
            --space-xxl: 6rem;
            --isLTR: 1;
            --isRTL: -1
        }

        .card {
            --title-color: grey;
            --time-left-color: teal;
            --hanzi-grid: #fafafa;
            --stroke: #555;
            --outline: #DDD;
            --drawing: #333;
            --pinyin-color: #ef6c00;
            --simplified-color: #6495ed;
            --traditional-color: #00796b;
            --meaning-color: #607d8b;
            --icon-button-background: #63759d;
            --icon-button-background-focus: #7d92c2;
            --sidebar-color: white;
            --sidebar-background-color: #52575d;
            --header-color: #455a64;
            --surface1: rgb(226, 226, 226);
            --surface2: rgb(255, 255, 254);
            --surface3: rgb(249, 249, 249);
            --surface4: rgb(212, 212, 212);
            --text1: rgb(48, 48, 48);
            --text2: rgb(94, 94, 94);
            --brand: rgb(47, 167, 214);
            --thumb-highlight-color: rgba(0, 0, 0, 0.2);
            font-size: 20px;
            text-align: center;
            color: black;
            background-color: white;
        }

        .card.night_mode {
            --header-color: white;
            --title-color: #00bcd4;
            --time-left-color: #fff;
            --hanzi-grid: #262626;
            --stroke: #ffffff;
            --outline: #5B5B5B;
            --drawing: #fff;
            --pinyin-color: #27b46e;
            --simplified-color: #6495ed;
            --traditional-color: #fba910;
            --meaning-color: #00BFA5;
            --icon-button-background: #63759d;
            --icon-button-background-focus: #7d92c2;
            --sidebar-color: white;
            --sidebar-background-color: #52575d;
            --surface1: rgb(27, 27, 27);
            --surface2: rgb(37, 37, 37);
            --surface3: rgb(48, 48, 48);
            --surface4: rgb(59, 59, 59);
            --text1: rgb(240, 240, 240);
            --text2: rgb(184, 184, 184);
            --brand: rgb(118, 161, 184);
            color: white;
            background-color: #1f1f1f;
        }

        .char-card {
            font-size: 3em;
        }

        /* Windows */
        .win .char-card {
            font-family: 'AR PL KaitiM GB', 'AR PL KaitiM Big5', 'Kaiti', 'KaiTi', '楷体', '楷體';
        }
        /* macOS */
        .mac .char-card {
            font-family: 'AR PL KaitiM GB', 'AR PL KaitiM Big5', 'Kaiti', 'KaiTi', '楷体', '楷體';
        }
        /* Linux desktops */
        .linux:not(.android) .char-card {
            font-family: 'AR PL KaitiM GB', 'AR PL KaitiM Big5', 'Kaiti', 'KaiTi', '楷体', '楷體';
        }

        /* --- Updated for Sidebar --- */
        .more-info-sidebar {
            height: 100%;
            width: 0;
            position: fixed;
            z-index: 10;
            top: 0;
            background-color: var(--surface2);
            overflow-x: hidden;
            transition: 0.5s;
            -webkit-tap-highlight-color: transparent;
            padding-top: 60px; /* Add padding for close button */
        }

        /* Default is RIGHT sidebar */
        #myMoreInfoSidebar {
            right: 0;
            box-shadow: -5px 0 15px rgba(0,0,0,0.2);
        }

        /* NEW Left sidebar */
        .left-sidebar {
            left: 0;
            box-shadow: 5px 0 15px rgba(0,0,0,0.2);
        }


        .more-info-sidebar a {
            padding: 8px 8px 8px 32px;
            text-decoration: none;
            font-size: 18px;
            color: var(--text1);
            display: block;
            transition: 0.3s;
            text-align: left;
        }

        .more-info-sidebar a:hover {
            background-color: var(--surface3);
            color: var(--brand);
        }

        .more-info-sidebar .closebtn {
            position: absolute;
            top: 0;
            right: 25px;
            font-size: 36px;
            margin-left: 50px;
        }

        /* NEW: Styles for toggle buttons INSIDE the sidebar */
        .more-info-sidebar .toggle-button {
            font-size: 18px; /* Match other links */
            color: var(--text1);
            background-color: transparent;
            border: none;
            box-shadow: none;
            padding: 8px 8px 8px 32px;
            width: 100%;
            text-align: left;
            border-radius: 0;
            font-weight: normal; /* Override bold */
        }

        .more-info-sidebar .toggle-button:hover {
            background-color: var(--surface3);
            color: var(--brand);
            box-shadow: none; /* Override hover shadow */
        }

        /* --- End Sidebar --- */

        /* --- Added for Controls --- */
        .controls-container {
            margin-top: 20px;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 10px;
        }

        .toggle-button {
            display: inline-block;
            padding: 8px 12px;
            font-size: 14px;
            font-weight: bold;
            color: var(--text2);
            background-color: var(--surface3);
            border: 1px solid var(--surface4);
            border-radius: 8px;
            text-decoration: none;
            transition: all 0.3s ease;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24);
            cursor: pointer;
        }

        .toggle-button:hover {
            background-color: var(--surface4);
            color: var(--text1);
            box-shadow: 0 2px 4px rgba(0,0,0,0.15);
        }

        /* --- REMOVED Toggle Options Panel --- */

        /* --- Added for Audio Button --- */
        /* This styles Anki's default audio button */
        #char_audio .replay-button {
            display: inline-block;
            width: 40px;
            height: 40px;
            background-color: var(--brand);
            border-radius: 50%;
            margin-top: 15px;
            cursor: pointer;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            transition: all 0.3s ease;
        }

        #char_audio .replay-button svg {
            fill: white;
            width: 24px;
            height: 24px;
            margin: 8px; /* Center the SVG */
        }

        #char_audio .replay-button:hover {
            background-color: var(--pinyin-color); /* Use a theme color */
            transform: scale(1.1);
        }

        /* grid color for character */
        .grid-color {
            margin: 6px;
            background-color: var(--hanzi-grid);
            padding: 2px;
            -webkit-box-shadow: 0px 0px 10px -5px rgba(0, 0, 0, 0.5);
            -moz-box-shadow: 0px 0px 10px -5px rgba(0, 0, 0, 0.5);
            box-shadow: 0px 0px 10px -5px rgba(0, 0, 0, 0.5);
        }

        .stroke-color {
            color: var(--stroke);
        }

        .outline-color {
            color: var(--outline);
        }

        .drawing-color {
            color: var(--drawing);
        }

        /* bottom button */
        .modal-footer1 {
            padding-top: 15px;
            text-align: center;
        }

        .modal-footer1 a {
            display: inline-block;
            margin: 0 8px;
            float: none;
        }

        .text-color1 {
            font-size: 16px;
            color: var(--pinyin-color);
        }

        .text-color2 {
            color: var(--traditional-color);
        }

        .text-color3 {
            color: var(--meaning-color);
        }

        .text-color4 {
            font-size: 30px;
            font-weight: bold;
            color: var(--simplified-color);
        }

        .practice-ch {
            border-radius: 6px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24);
            transition: all 0.3s ease;
            padding: 3px;
        }

        .tone1 {
            color: #F44336;
        }

        .tone2 {
            color: #FBC02D;
        }

        .tone3 {
            color: #4CAF50;
        }

        .tone4 {
            color: #03A9F4;
        }

        .tone5 {
            color: #858585;
        }

        /* --- UPDATED & NEW STYLES --- */

        .meanings-container {
            margin-top: 15px;
            text-align: left;
            max-width: 500px;
            margin-left: auto;
            margin-right: auto;
        }

        .meaning-card {
            padding: 10px;
            font-size: 1.1em;
            color: var(--text1);
            background-color: var(--surface3);
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .meaning-label {
            font-weight: bold;
            color: var(--meaning-color);
            display: block;
            font-size: 0.9em;
            margin-bottom: 4px;
        }

        .examples-container {
            margin-top: 20px;
            text-align: left;
            max-width: 500px;
            margin-left: auto;
            margin-right: auto;
            font-size: 1.1em;
        }

        .example-group {
            padding: 12px;
            background-color: var(--surface1);
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .example-sentence {
            color: var(--text1);
            font-style: italic;
        }

        .extras-group {
            margin-top: 15px;
            padding: 12px;
            background-color: var(--surface3);
            border: 1px dashed var(--surface4);
            border-radius: 8px;
        }

        .extras-header {
            font-weight: bold;
            color: var(--brand);
            font-size: 0.9em;
            margin-bottom: 5px;
        }

        .extras-content {
            color: var(--text2);
            font-size: 1em;
            /* This allows line breaks from Anki field to render */
            white-space: pre-wrap; 
        }


        /* --- Original Styles --- */

        .char {
            font-size: 30px;
        }

        .pinyin {
            font-size: 1.5em;
            color: var(--pinyin-color);
            margin-bottom: 10px;
        }

        .zhuyin {
            font-size: 16px;
        }

        .py {
            font-size: 14px;
            color: gray;
        }

        .zy {
            font-size: 14px;
            color: gray;
        }

        .header {
            color: var(--header-color);
            font-size: 0.9em;
        }

        .question-sub-text {
            color: #f44336;
            font-weight: bold;
        }

        .char-tone1 {
            color: var(--tone-1);
        }


        .char-tone2 {
            color: var(--tone-2);
        }


        .char-tone3 {
            color: var(--tone-3);
        }


        .char-tone4 {
            color: var(--tone-4);
        }

        .char-sim-1 {
            margin: 2px;
            font-size: 30px;
        }

        .char-trad-1 {
            margin: 2px;
            font-size: 30px;
        }

        .char-pin-1 {
            margin: 2px;
            line-height: 32px;
        }

        .char-zhy-1 {
            margin: 2px;
            line-height: 32px;
        }

        small {
            line-height: 1.5;
        }

        hr {
            border: 0;
            height: 0;
            border-bottom: 1px solid var(--surface4);
            margin: 1em 0;
        }
""",
    # 5. Tag Rules: Auto-generates tags from the 'categories' column
    "tag_rules_yaml": """
- static_tags:
    - "Chinese"
    - "Pipeline"
- prefix: "Category"
  # column: "categories" # Matches the CSV column # This is giving error for it im commenting, fix in the future
  split_by: ","
  # Cleans up the "['...']" format from the CSV
  strip: ' []''"' 
""",
}


def render_anki_tab():
    """
    Renders the 'Anki Deck Generator' tab.
    """
    from deck_generator import DeckGenerator

    st.header("Anki Deck Generator")

    # --- Initialize Session State for Config ---
    if "anki_config" not in st.session_state:
        st.session_state.anki_config = {
            "model_id": 1607392319,
            "model_name": "AURCODE Refactored Model",
            "deck_id": 1234567890,
            "note_type": "Vocabulary",
            # This list defines the Anki fields (no change)
            "model_fields": [
                {"name": "Front"},
                {"name": "Back"},
                {"name": "Example"},
                {"name": "Audio"},
                {"name": "Image"},
                {"name": "Notes"},
            ],
            # UPDATED: This now matches your pipeline output CSV by default
            "model_builder": [
                {"csv_column": "Word"},  # Maps to Front
                {"csv_column": "Definition"},  # Maps to Back
                {"csv_column": "Sentence"},  # Maps to Example
                {"csv_column": "Sound"},  # Maps to Audio
                {"csv_column": "Picture"},  # Maps to Image (a non-existent col is fine)
                {"csv_column": "Category"},  # Maps to Notes
            ],
            # UPDATED: This now matches your pipeline output CSV by default
            "media_fields": [
                {"column_name": "Sound", "media_type": "audio"},
                {"column_name": "Picture", "media_type": "image"},
            ],
            "model_templates_yaml": DEFAULT_MODEL_TEMPLATES_YAML,
            "tag_rules_yaml": DEFAULT_TAG_RULES_YAML,  # This now uses the new default
        }

    cfg = st.session_state.anki_config

    anki_col1, anki_col2 = st.columns([0.6, 0.4])

    with anki_col1:
        st.subheader("1. Deck Configuration")

        with st.expander("Basics"):
            cfg["model_id"] = st.number_input("Model ID", value=cfg["model_id"], step=1)
            cfg["model_name"] = st.text_input("Model Name", value=cfg["model_name"])
            cfg["deck_id"] = st.number_input("Deck ID", value=cfg["deck_id"], step=1)
            cfg["note_type"] = st.text_input("Note Type", value=cfg["note_type"])

        with st.expander("Field Mapping (CSV -> Anki)"):
            st.markdown(
                "Define Anki fields, then map CSV columns to them. **Order must match!**"
            )
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Anki Model Fields**")
                cfg["model_fields"] = st.data_editor(
                    pd.DataFrame(cfg["model_fields"]), num_rows="dynamic"
                )
            with c2:
                st.markdown("**CSV Column Mapping**")
                cfg["model_builder"] = st.data_editor(
                    pd.DataFrame(cfg["model_builder"]), num_rows="dynamic"
                )

        with st.expander("Media Fields"):
            st.markdown("Define which CSV columns contain media filenames.")
            cfg["media_fields"] = st.data_editor(
                pd.DataFrame(cfg["media_fields"]), num_rows="dynamic"
            )

        with st.expander("Advanced: Templates (YAML)"):
            cfg["model_templates_yaml"] = st.text_area(
                "Model Templates", value=cfg["model_templates_yaml"], height=300
            )

        with st.expander("Advanced: Tag Rules (YAML)"):
            cfg["tag_rules_yaml"] = st.text_area(
                "Tag Rules", value=cfg["tag_rules_yaml"], height=250
            )

    with anki_col2:
        st.subheader("2. Input Data")

        # --- NEW: "Chinese Setup" Button ---
        if st.button(
            "Load 🇨🇳 Chinese Pipeline Setup",
            help="Click to auto-fill all fields for the standard pipeline CSV output",
            use_container_width=True,
        ):
            # Update all config fields in session state
            for key, value in CHINESE_PIPELINE_SETUP.items():
                st.session_state.anki_config[key] = value

            st.success("Loaded Chinese Pipeline setup!")
            st.rerun()  # Rerun to reflect changes in all widgets
        # --- End of New Button ---

        uploaded_csv = st.file_uploader(
            "Upload Vocabulary CSV", type=["csv"], key="anki_csv_uploader"
        )
        deck_name = st.text_input("Deck Name", value="My Anki Deck")
        output_dir = st.text_input("Output Directory", value="output/")

        st.divider()
        st.subheader("3. Generate")

        if st.button(
            "Generate Anki Deck (.apkg)", type="primary", use_container_width=True
        ):
            # --- 1. PRE-VALIDATION ---
            # We will collect all config errors and show them at once.
            errors = []

            # 1a. Check for required file and text inputs
            if not uploaded_csv:
                st.warning("Please upload a vocabulary CSV file.")
                # We return here because we can't validate the CSV-dependent
                # configs below without a file.
                return

            if not deck_name:
                errors.append("Please provide a 'Deck Name'.")

            if not output_dir:
                errors.append("Please provide an 'Output Directory'.")

            # 1b. Validate YAML parsing
            try:
                model_templates_dict = yaml.safe_load(cfg["model_templates_yaml"])
                if not isinstance(model_templates_dict, dict):
                    errors.append(
                        "'Model Templates' YAML is invalid (must be a dictionary)."
                    )
            except yaml.YAMLError as e:
                errors.append(f"Error parsing 'Model Templates' YAML: {e}")
                model_templates_dict = None

            try:
                tag_rules_list = yaml.safe_load(cfg["tag_rules_yaml"])
                if not isinstance(tag_rules_list, list):
                    errors.append("'Tag Rules' YAML is invalid (must be a list).")
            except yaml.YAMLError as e:
                errors.append(f"Error parsing 'Tag Rules' YAML: {e}")
                tag_rules_list = None

            # 1c. Validate DataFrame-based configs
            model_fields_df = cfg["model_fields"]
            model_builder_df = cfg["model_builder"]
            media_fields_df = cfg["media_fields"]  # OK if this one is empty

            if model_fields_df.empty:
                errors.append("'Anki Model Fields' cannot be empty.")

            if model_builder_df.empty:
                errors.append("'CSV Column Mapping' cannot be empty.")

            # 1d. Check for logic errors (mismatched lengths)
            if not model_fields_df.empty and not model_builder_df.empty:
                if len(model_fields_df) != len(model_builder_df):
                    errors.append(
                        f"Field mismatch: You have {len(model_fields_df)} 'Anki Model Fields' "
                        f"but {len(model_builder_df)} 'CSV Column Mappings'. These must be equal."
                    )

            # --- 2. EXECUTION ---
            # If we found any errors, show them and stop.
            if errors:
                st.error("Please fix the following configuration errors:")
                for err in errors:
                    st.error(f"- {err}")
                return  # Stop execution!

            # If all checks passed, proceed with generation
            try:
                with st.spinner("Generating Anki Deck..."):
                    # 1. Load Data
                    logger.info(f"Reading data from uploaded file: {uploaded_csv.name}")
                    df = pd.read_csv(uploaded_csv)
                    df = df.astype(object).where(pd.notnull(df), None)  # Replace NaN

                    # 2. Assemble Config (using validated variables)
                    logger.info("Assembling configuration from UI...")
                    config_dict = {
                        "basics": {
                            # Explicitly cast to int to be defensive.
                            # st.number_input can return float (e.g., 123.0)
                            "model_id": int(cfg["model_id"]),
                            "model_name": cfg["model_name"],
                            "deck_id": int(cfg["deck_id"]),
                            "note_type": cfg["note_type"],
                        },
                        "model_fields": model_fields_df.to_dict("records"),
                        "model_builder": model_builder_df["csv_column"].tolist(),
                        "media_fields": media_fields_df.to_dict("records"),
                        "model_templates": model_templates_dict,  # Use parsed dict
                        "tag_rules": tag_rules_list,  # Use parsed list
                    }

                    # 3. Write temp config
                    temp_config_file = Path("temp_anki_config.yaml")
                    with open(temp_config_file, "w", encoding="utf-8") as f:
                        yaml.dump(config_dict, f, allow_unicode=True)

                    # 4. Ensure output dir exists
                    output_path = Path(output_dir)
                    output_path.mkdir(exist_ok=True)

                    # 5. Initialize Generator and Run
                    logger.info("Initializing DeckGenerator...")
                    generator = DeckGenerator(config_path=temp_config_file)

                    logger.info(f"Generating deck '{deck_name}'...")
                    generator.generate_deck(
                        df=df,
                        deck_name=deck_name,
                        output_path=output_path,
                        strict=False,
                    )

                    deck_file_path = output_path / f"{deck_name}.apkg"

                    # 6. Clean up temp file
                    temp_config_file.unlink()

                    if deck_file_path.exists():
                        st.success(f"Deck '{deck_name}.apkg' generated successfully!")
                        # 7. Provide download
                        with open(deck_file_path, "rb") as f:
                            st.download_button(
                                label=f"Download {deck_name}.apkg",
                                data=f.read(),
                                file_name=f"{deck_name}.apkg",
                                mime="application/octet-stream",
                                use_container_width=True,
                            )
                    else:
                        st.error(
                            "Deck generation finished, but no .apkg file was found."
                        )

            except Exception as e:
                # This will still catch the error you saw, but now
                # we know it's not a simple config error.
                logger.critical(f"An error occurred during deck generation: {e}")
                st.error(f"An unexpected error occurred: {e}")
                # Clean up temp file on error too
                if "temp_config_file" in locals() and temp_config_file.exists():
                    temp_config_file.unlink()
