"""Chinese pipeline templates for Anki deck generation."""

CHINESE_PIPELINE_MODEL_TEMPLATES_YAML = """
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

        {{#Image}}
        <div class="extras-group">
        <div class="extras-header">Image</div>
        <div class="extras-content">{{Image}}</div>
        </div>
        {{/Image}}

        <!-- Examples Section (Only shows if fields are not empty) -->
        <div class="examples-container">
        <div class="examples-header">📚 Example Sentences</div>
        {{#Example 1}}
        <div class="example-card">
        <div class="example-number">1</div>
        <div class="example-content">
        <div class="example-sentence clickable-sentence" onclick="playAudio('example1')">{{Example 1}}</div>
        {{#Example 1 Audio}}
        <div class="audio-controls">
        <button class="play-button" onclick="playAudio('example1')" title="Play audio">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
        <path d="M8 5v14l11-7z"/>
        </svg>
        </button>
        <span class="audio-label">🔊 Click sentence or button to play</span>
        </div>
        <div id="example1-audio" style="display:none;">{{Example 1 Audio}}</div>
        {{/Example 1 Audio}}
        </div>
        </div>
        {{/Example 1}}
        {{#Example 2}}
        <div class="example-card">
        <div class="example-number">2</div>
        <div class="example-content">
        <div class="example-sentence clickable-sentence" onclick="playAudio('example2')">{{Example 2}}</div>
        {{#Example 2 Audio}}
        <div class="audio-controls">
        <button class="play-button" onclick="playAudio('example2')" title="Play audio">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
        <path d="M8 5v14l11-7z"/>
        </svg>
        </button>
        <span class="audio-label">🔊 Click sentence or button to play</span>
        </div>
        <div id="example2-audio" style="display:none;">{{Example 2 Audio}}</div>
        {{/Example 2 Audio}}
        </div>
        </div>
        {{/Example 2}}
        {{#Example 3}}
        <div class="example-card">
        <div class="example-number">3</div>
        <div class="example-content">
        <div class="example-sentence clickable-sentence" onclick="playAudio('example3')">{{Example 3}}</div>
        {{#Example 3 Audio}}
        <div class="audio-controls">
        <button class="play-button" onclick="playAudio('example3')" title="Play audio">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
        <path d="M8 5v14l11-7z"/>
        </svg>
        </button>
        <span class="audio-label">🔊 Click sentence or button to play</span>
        </div>
        <div id="example3-audio" style="display:none;">{{Example 3 Audio}}</div>
        {{/Example 3 Audio}}
        </div>
        </div>
        {{/Example 3}}

        {{#All Sentences}}
        <div class="extras-group">
        <div class="extras-header">All Generated Sentences</div>
        <div class="extras-content">{{All Sentences}}</div>
        </div>
        {{/All Sentences}}

        {{#Part of Speech}}
        <div class="extras-group">
        <div class="extras-header">Part of Speech</div>
        <div class="extras-content">{{Part of Speech}}</div>
        </div>
        {{/Part of Speech}}

        {{#Character Breakdown}}
        <div class="extras-group">
        <div class="extras-header">Character Breakdown</div>
        <div class="extras-content">{{Character Breakdown}}</div>
        </div>
        {{/Character Breakdown}}

        {{#Detailed Explanation (EN)}}
        <div class="extras-group">
        <div class="extras-header">Detailed Explanation (EN)</div>
        <div class="extras-content">{{Detailed Explanation (EN)}}</div>
        </div>
        {{/Detailed Explanation (EN)}}

        {{#Detailed Explanation (ES)}}
        <div class="extras-group">
        <div class="extras-header">Detailed Explanation (ES)</div>
        <div class="extras-content">{{Detailed Explanation (ES)}}</div>
        </div>
        {{/Detailed Explanation (ES)}}

        {{#Synonyms}}
        <div class="extras-group">
        <div class="extras-header">Synonyms</div>
        <div class="extras-content">{{Synonyms}}</div>
        </div>
        {{/Synonyms}}

        {{#Antonyms}}
        <div class="extras-group">
        <div class="extras-header">Antonyms</div>
        <div class="extras-content">{{Antonyms}}</div>
        </div>
        {{/Antonyms}}

        {{#Collocations}}
        <div class="extras-group">
        <div class="extras-header">Collocations</div>
        <div class="extras-content">{{Collocations}}</div>
        </div>
        {{/Collocations}}

        {{#Edge Case Notes}}
        <div class="extras-group">
        <div class="extras-header">Edge Case Notes</div>
        <div class="extras-content">{{Edge Case Notes}}</div>
        </div>
        {{/Edge Case Notes}}

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
        if(void 0===window.Persistence){var e="[github.com/SimonLammer/anki-persistence/](https://github.com/SimonLammer/anki-persistence/)",t="_default";if(window.Persistence_localStorage=function(){var i=!1;try{null!==window.localStorage&&"object"==typeof window.localStorage&&(i=!0,this.clear=function(){for(var t=0;t<localStorage.length;t++){var i=localStorage.key(t);0==i.indexOf(e)&&(localStorage.removeItem(i),t--)}},this.setItem=function(i,n){void 0==n&&(n=i,i=t),localStorage.setItem(e+i,JSON.stringify(n))},this.getItem=function(i){return void 0==i&&(i=t),JSON.parse(localStorage.getItem(e+i))},this.removeItem=function(i){void 0==i&&(i=t),localStorage.removeItem(e+i)})}catch(n){}this.isAvailable=function(){return i}},window.Persistence_sessionStorage=function(){var i=!1;try{"object"==typeof window.sessionStorage&&(i=!0,this.clear=function(){for(var t=0;t<sessionStorage.length;t++){var i=sessionStorage.key(t);0==i.indexOf(e)&&(sessionStorage.removeItem(i),t--)}},this.setItem=function(i,n){void 0==n&&(n=i,i=t),sessionStorage.setItem(e+i,JSON.stringify(n))},this.getItem=function(i){return void 0==i&&(i=t),JSON.parse(sessionStorage.getItem(e+i))},this.removeItem=function(i){void 0==i&&(i=t),sessionStorage.removeItem(e+i)})}catch(n){}this.isAvailable=function(){return i}},window.Persistence_windowKey=function(i){var n=window[i],o=!1;"object"==typeof n&&(o=!0,this.clear=function(){n[e]={}},this.setItem=function(i,o){void 0==o&&(o=i,i=t),n[e][i]=o},this.getItem=function(i){return void 0==i&&(i=t),void 0==n[e][i]?null:n[e][i]},this.removeItem=function(i){void 0==i&&(i=t),delete n[e][i]},void 0==n[e]&&this.clear()),this.isAvailable=function(){return o}},window.Persistence=new Persistence_sessionStorage,navigator.userAgent.indexOf("Mobile")>0&&(window.Persistence=new Persistence_localStorage,Persistence.isAvailable()||(window.Persistence=new Persistence_sessionStorage)),Persistence.isAvailable()||(Persistence=new Persistence_windowKey("py")),!Persistence.isAvailable()){var i=window.location.toString().indexOf("title"),n=window.location.toString().indexOf("main",i);i>0&&n>0&&n-i<10&&(window.Persistence=new Persistence_windowKey("qt"))}}
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

        // --- AUDIO PLAYBACK FUNCTIONS ---
        var currentlyPlaying = null;

        function playAudio(exampleId) {
            console.log("Playing audio for: " + exampleId);
            
            // Stop any currently playing audio
            if (currentlyPlaying) {
                stopAudio(currentlyPlaying);
            }
            
            var audioDiv = document.getElementById(exampleId + '-audio');
            var sentence = document.querySelector('[onclick="playAudio(\'' + exampleId + '\')"]');
            var playButton = document.querySelector('[onclick="playAudio(\'' + exampleId + '\')"].play-button');
            
            if (!audioDiv || !audioDiv.innerHTML.trim()) {
                console.log("No audio found for: " + exampleId);
                return;
            }
            
            try {
                // Get the audio file path from the hidden div
                var audioPath = audioDiv.innerHTML.trim();
                console.log("Audio path: " + audioPath);
                
                // Create audio element if it doesn't exist
                if (!audioDiv.audioElement) {
                    audioDiv.audioElement = new Audio(audioPath);
                    audioDiv.audioElement.addEventListener('ended', function() {
                        stopAudio(exampleId);
                    });
                    audioDiv.audioElement.addEventListener('error', function(e) {
                        console.error("Audio playback error:", e);
                        stopAudio(exampleId);
                    });
                }
                
                // Add visual feedback
                if (sentence) {
                    sentence.classList.add('sentence-playing');
                }
                if (playButton) {
                    playButton.classList.add('playing');
                }
                
                // Play the audio
                audioDiv.audioElement.currentTime = 0;
                audioDiv.audioElement.play();
                
                currentlyPlaying = exampleId;
                console.log("Audio started playing for: " + exampleId);
                
            } catch (error) {
                console.error("Error playing audio:", error);
                stopAudio(exampleId);
            }
        }

        function stopAudio(exampleId) {
            console.log("Stopping audio for: " + exampleId);
            
            var audioDiv = document.getElementById(exampleId + '-audio');
            var sentence = document.querySelector('[onclick="playAudio(\'' + exampleId + '\')"]');
            var playButton = document.querySelector('[onclick="playAudio(\'' + exampleId + '\')"].play-button');
            
            // Remove visual feedback
            if (sentence) {
                sentence.classList.remove('sentence-playing');
            }
            if (playButton) {
                playButton.classList.remove('playing');
            }
            
            // Stop and reset audio
            if (audioDiv && audioDiv.audioElement) {
                audioDiv.audioElement.pause();
                audioDiv.audioElement.currentTime = 0;
            }
            
            if (currentlyPlaying === exampleId) {
                currentlyPlaying = null;
            }
            
            console.log("Audio stopped for: " + exampleId);
        }

        // Add keyboard shortcuts
        document.addEventListener('keydown', function(event) {
            if (event.key === '1') playAudio('example1');
            else if (event.key === '2') playAudio('example2');
            else if (event.key === '3') playAudio('example3');
        });

        // Add touch feedback for mobile
        document.addEventListener('touchstart', function(event) {
            if (event.target.classList.contains('clickable-sentence')) {
                event.target.style.transform = 'scale(0.98)';
            }
        });

        document.addEventListener('touchend', function(event) {
            if (event.target.classList.contains('clickable-sentence')) {
                setTimeout(function() {
                    event.target.style.transform = '';
                }, 150);
            }
        });
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

        .example-audio {
            margin-top: 8px;
            text-align: center;
        }

        .example-audio .replay-button {
            display: inline-block;
            width: 30px;
            height: 30px;
            background-color: var(--brand);
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            transition: all 0.3s ease;
        }

        .example-audio .replay-button svg {
            fill: white;
            width: 18px;
            height: 18px;
            margin: 6px;
        }

        .example-audio .replay-button:hover {
            background-color: var(--pinyin-color);
            transform: scale(1.1);
        }

        /* --- NEW ENHANCED STYLES FOR INTERACTIVE SENTENCES --- */

        .examples-header {
            font-size: 1.3em;
            font-weight: bold;
            color: var(--brand);
            margin-bottom: 15px;
            text-align: center;
            padding: 10px;
            background: var(--surface2);
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .example-card {
            display: flex;
            align-items: flex-start;
            background: var(--surface2);
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            border-left: 4px solid var(--brand);
        }

        .example-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        }

        .example-number {
            background: var(--brand);
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 1.1em;
            margin-right: 15px;
            flex-shrink: 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }

        .example-content {
            flex: 1;
        }

        .clickable-sentence {
            font-size: 1.2em;
            color: var(--text1);
            background: var(--surface3);
            padding: 12px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-bottom: 10px;
            border: 2px solid transparent;
            position: relative;
            overflow: hidden;
        }

        .clickable-sentence:hover {
            background: var(--surface4);
            border-color: var(--brand);
            transform: scale(1.02);
        }

        .clickable-sentence:active {
            transform: scale(0.98);
        }

        .clickable-sentence::before {
            content: "🔊";
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            opacity: 0.7;
            font-size: 1.1em;
        }

        .clickable-sentence:hover::before {
            opacity: 1;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { transform: translateY(-50%) scale(1); }
            50% { transform: translateY(-50%) scale(1.1); }
            100% { transform: translateY(-50%) scale(1); }
        }

        .audio-controls {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 8px;
        }

        .play-button {
            background: var(--brand);
            color: white;
            border: none;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }

        .play-button:hover {
            background: var(--pinyin-color);
            transform: scale(1.1);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }

        .play-button:active {
            transform: scale(0.95);
        }

        .play-button.playing {
            background: var(--tone-2);
            animation: playing 1s infinite;
        }

        @keyframes playing {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }

        .audio-label {
            color: var(--text2);
            font-size: 0.9em;
            font-style: italic;
        }

        .sentence-playing {
            background: linear-gradient(135deg, var(--surface3), var(--brand)20) !important;
            border-color: var(--brand) !important;
            animation: glow 1.5s ease-in-out infinite alternate;
        }

        @keyframes glow {
            from { box-shadow: 0 0 5px var(--brand); }
            to { box-shadow: 0 0 20px var(--brand); }
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
"""
