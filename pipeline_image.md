Lord of the Mysteries: Flashcard Generation Pipeline

System Overview

This pipeline converts 2-3 character Chinese vocabulary words into highly consistent, text-free, 1:1 Victorian-style images for language learning.

It is a two-stage process:

Stage 1 (Text LLM): Analyzes the Chinese word, determines its conceptual category, and writes a highly evocative English visual description using the System Prompt below.

Stage 2 (Image Model): Renders the final Master Image Prompt into a 1x1 image using tools like Midjourney, DALL-E 3, or Stable Diffusion.

Stage 1: The "Visual Translator" System Prompt

Copy and paste this into your text LLM (ChatGPT, Claude, etc.) to set it up to write descriptions for you.

System Prompt: Flashcard Visual Translator

Role: You are an expert prompt engineer and visual designer specializing in the "Lord of the Mysteries" (诡秘之主) universe.

Task: I will provide you with a Chinese vocabulary word (usually 2-3 characters). Your job is to create a specific, highly evocative English visual description of that word and embed it into a strict Master Image Prompt template.

Rules for Visual Descriptions:

Concrete Nouns (e.g., 左轮手枪): Describe the object with intense Victorian/Steampunk detail (e.g., textures like dark mahogany, tarnished brass, deep shadows).

Verbs/Actions (e.g., 书写): Describe a close-up action dynamically without showing full faces (e.g., hands in motion, dramatic lighting).

Abstract/Grammar (e.g., 彻底, 诡秘): Invent a clever physical metaphor. Do not use text, symbols (+, &), or modern concepts. Rely heavily on the gaslamp fantasy aesthetic.

Proper Nouns (e.g., 克莱恩): Describe the character's physical traits as a moody, atmospheric portrait.

The Master Template:
Once you have the visual description, you MUST output ONLY the following exact template, replacing [INSERT VISUAL DESCRIPTION HERE] with your english description:

"A highly detailed, conceptual illustration specifically designed as a language learning vocabulary flashcard. The central image visually represents: 

$$INSERT VISUAL DESCRIPTION HERE$$

.

Style Requirements: A strong Victorian gaslamp fantasy aesthetic. The object should feature ornate gothic details, tarnished brass, dark mahogany, and intricate engravings. Use a moody, rich color palette with dramatic, high-contrast rim lighting to make the subject look three-dimensional and premium.

Background & Framing: The subject must be strictly isolated and centered tightly on a solid, uniform, pale aged-ivory background (hex code #F8F5EE) to ensure maximum contrast.

Formatting & Constraints: The image must be strictly a 1:1 square aspect ratio. The image is COMPLETELY TEXT-FREE: absolutely no letters, no Chinese characters, no words, no labels, no speech bubbles, and no signage. Purely a visual representation."

Stage 2: The Master Image Prompt

This is the final prompt that goes into your image generator.

A highly detailed, conceptual illustration specifically designed as a language learning vocabulary flashcard. The central image visually represents: 

$$INSERT VISUAL DESCRIPTION HERE$$

.

Style Requirements: A strong Victorian gaslamp fantasy aesthetic. The object should feature ornate gothic details, tarnished brass, dark mahogany, and intricate engravings. Use a moody, rich color palette with dramatic, high-contrast rim lighting to make the subject look three-dimensional and premium.

Background & Framing: The subject must be strictly isolated and centered tightly on a solid, uniform, pale aged-ivory background (hex code #F8F5EE) to ensure maximum contrast.

Formatting & Constraints: The image must be strictly a 1:1 square aspect ratio. The image is COMPLETELY TEXT-FREE: absolutely no letters, no Chinese characters, no words, no labels, no speech bubbles, and no signage. Purely a visual representation.

Master Vocabulary List: Curated High-Detail Examples

Replace [INSERT VISUAL DESCRIPTION HERE] in the Master Prompt with the English text below. These examples demonstrate the level of descriptive depth required for the best image results.

Category 1: Concrete Objects & Body Parts

左轮手枪 (Revolver): a heavily worn, antique Victorian revolver with a dark, polished mahogany grip, intricate gothic engravings swirling along the tarnished brass barrel, and a faint wisp of smoke curling from the muzzle

墨水瓶 (Ink bottle): an ornate, heavy glass inkwell shaped like a faceted raven's skull, capped with tarnished brass, sitting in a small pool of spilled, glistening dark crimson ink

穿衣镜 (Mirror): an imposing, tall Victorian full-length mirror enclosed in a deeply carved, dark mahogany frame featuring twisted vines, reflecting a misty, gaslit room obscured by thick shadows

Category 2: Verbs & Actions

书写 (Write): a macro close-up of a sharp, elegant black-feathered quill pen violently scratching across thick, yellowed parchment, leaving a trail of dripping, dark crimson ink

摆脱 / 控制 (Break free/Control): a dramatic close-up of two pale hands violently snapping thick, rusted iron chains, with sparks flying in the dim, warm light of a nearby gaslamp

醒 (Wake): a surreal conceptual depiction of a human face where the top half is slowly dissolving into swirling, dark ethereal mist, while the bottom half remains sharp and illuminated by warm, flickering gaslight

Category 3: Adjectives, Colors & Vibe

诡秘 (Mysterious): a single, glowing, unnatural crimson eye peering intensely through the keyhole of a massive, heavily padlocked, dark wooden door surrounded by swirling gray fog

泛黄 (Yellowed): a close-up of a highly textured, brittle piece of antique parchment, deeply stained with tea-colored age spots and burnt edges, resting on a dusty mahogany table

彻底 (Thoroughly/Completely): an elegant, delicate Victorian ceramic teacup captured in the exact moment of being shattered into a hundred tiny, irreparable fragments radiating outward in mid-air

Category 4: Conceptual Nouns

历史系 (History Dept): a grand, dusty mahogany pedestal bathed in a single beam of light, proudly displaying a stack of thick, leather-bound ancient tomes, rolled-up parchment scrolls with cracked wax seals, and a tarnished brass globe

话语 (Words): a stylized, glowing soundwave made of glittering golden dust particles, floating gracefully in the air above an open, ancient leather-bound book

边缘 (Edge): a heavy, ancient gold coin balancing precariously on the absolute razor-sharp edge of a gothic hunting knife's blade, emphasizing a dangerous and precarious boundary

Category 5: Proper Nouns (Lore Specific)

克莱恩 (Klein): a moody portrait of a scholarly young Victorian gentleman with short, neat black hair and perceptive light brown eyes, wearing a slightly worn, modest dark suit and a crisp white shirt, gazing forward thoughtfully

霍伊 (Hoy University): a dramatic, low-angle view of a grand, imposing gothic university building with towering spires, intricate stone gargoyles, and stained glass windows, set against a dark, stormy sky

Category 6: The "Do Not Generate" List

WARNING: Do not generate images for the following grammatical particles, prepositions, and vague quantifiers. Using abstract imagery for these will hinder your language learning. Use standard text flashcards with example sentences instead.

List: 与, 一个, 不会, 而, 于, 以, 以及, 想要, 觉, 之, 之中, 可, 心头, 一阵, 难以, 大半夜, 嘶, 看来, 将, 下意识, 这时, 下方, 一下, 连通, 半个.
