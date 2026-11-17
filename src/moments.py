"""Couple 'moments' library: each reel picks one moment, then a song that fits its mood, then the image draws it.

Each moment: key, name, mood (what kind of song fits), scene (what to draw), framing (camera; default mid-shot),
aliases (words accepted by the Telegram bot: /reel wall).
Rotation: least-recently-used first (from history.json), random among the unused ones.
All moments are intimate / sensual. Clothing is contemporary Western.
"""
import random

MID = 'shown large as a mid shot (head-and-torso), cropped by the bottom edge of the image'
FULL_SIT = ('shown as a seated / low full-figure shot filling the lower 60-65% of the frame, bodies cropped by '
            'the bottom edge where needed')
CLOSE = 'a close, tender framing of the bodies (no faces needed), filling the lower 60-65% of the frame'

MOMENTS = [
    # ---------------------------------------------------------------- charged closeness
    dict(key='almost-kiss', name='Foreheads touching, almost a kiss', aliases=['almost', 'kareebi'],
         mood='tension, anticipation, deep longing; slow burn romantic songs',
         scene='She wears a fitted off-shoulder black crop top and high-waisted cream linen trousers. He wears '
               'a loose grey linen shirt, top buttons open. Foreheads touching, eyes closed and hidden by her '
               'hair, noses almost touching; his hand cups the side of her jaw gently; both completely still, '
               'the moment just before.',
         framing=CLOSE),
    dict(key='wall-lean', name='He leans over her against a wall', aliases=['wall', 'deewar'],
         mood='tension, slow burn, intense closeness; deep longing romantic songs',
         scene='She wears a thin-strapped cream slip dress. He wears a charcoal grey button-down shirt, sleeves '
               'rolled. She stands with her back against a bare wall, one hand pressed flat on his chest; he '
               'leans in with one forearm raised against the wall above her, face angled down toward her neck — '
               'features lost in shadow; the air between them charged and completely still.',
         framing=CLOSE),
    dict(key='lying-over', name='He is propped over her on the bed', aliases=['over', 'upar'],
         mood='slow burn, suspended moment, completely absorbed; deep aching love songs',
         scene='She lies on her back on rumpled white sheets, wearing a satin slip or just a fitted ribbed '
               'tank top, her hair spread around her, face turned slightly to the side and veiled by hair; '
               'he is propped over her, one hand beside her head on the pillow, the other near her waist — '
               'his loose white shirt hanging open; both completely still, faces very close.',
         framing=CLOSE),
    dict(key='nose-nuzzle', name='Noses touching, breathing each other in', aliases=['nuzzle', 'saanson'],
         mood='quiet intimacy, completely lost in each other; breathy slow songs',
         scene='She wears a loose oversized grey sweatshirt off one shoulder. He wears a plain black tee. '
               'Noses just touching, eyes closed and hidden by hair, the faint silhouette of parted lips; '
               'his hand cradles the back of her head; her fingers curled into his shirt; both completely '
               'still, just breathing.',
         framing=CLOSE),
    dict(key='chin-tilt', name='He tilts her chin up with one finger', aliases=['chin', 'thaami'],
         mood='soft intensity, longing fulfilled; slow burn songs about finally being close',
         scene='She wears a fitted sleeveless ribbed top in dusty rose and wide-leg trousers. He wears a '
               'dark olive linen shirt. He hooks one finger gently under her chin and tilts her face toward '
               'him; she lets him, eyes lowered and hidden by her fringe, the faint silhouette of her lips '
               'slightly parted; he looks at her with quiet intensity, face in three-quarter profile.',
         framing=CLOSE),
    dict(key='jaw-cup', name='He cups her jaw, she leans into his hand', aliases=['jaw', 'rukhna'],
         mood='tender, adoring, deep devotion; slow emotional songs',
         scene='She wears a loose off-shoulder black knit top. He wears a cream linen button-down. Close and '
               'still: he cups the side of her face gently in one large hand; she closes her eyes and leans '
               'into his palm completely, both her hands holding his wrist; her hair falls forward over her '
               'eyes; a single warm side-light.',
         framing=CLOSE),
    # ---------------------------------------------------------------- pulling close
    dict(key='waist-pull', name='He pulls her close by the waist', aliases=['pull', 'kareeb'],
         mood='pull, longing, slow tension; deep aching romantic songs',
         scene='She wears a muted cream cotton crop top and high-waisted charcoal trousers. He wears a '
               'dark grey linen shirt. He hooks his hand firmly around her waist and draws her toward him; '
               'she turns, one palm pressed flat on the centre of his chest; their faces hover inches apart, '
               'the faint silhouette of her parted lips, her long hair cascading forward to veil her eyes.',
         framing=CLOSE),
    dict(key='shirt-grip', name='She grips his shirt and pulls him closer', aliases=['grip', 'thaamo'],
         mood='longing, need, raw emotion; emotionally raw love songs',
         scene='She wears a thin-strapped olive slip dress. He wears a loose white linen shirt. She has '
               'both fists curled tight around the front of his shirt and pulls him toward her; he comes '
               'willingly, hand on the wall behind her; her face is turned down and hidden by falling hair; '
               'the moment urgent and completely quiet.',
         framing=CLOSE),
    dict(key='dupatta-slip', name='He slides her top strap off her shoulder', aliases=['strap', 'aanchal'],
         mood='slow, sensual, unhurried; hushed love songs',
         scene='She wears a thin-strapped satin slip dress in ivory. He wears a plain charcoal t-shirt. '
               'Standing close, he draws one thin strap slowly off her shoulder with his fingertips; it '
               'slips and bares her shoulder; she looks slightly to the side and down, one hand raised to '
               'rest lightly on his; both still, the air very quiet.',
         framing=CLOSE),
    # ---------------------------------------------------------------- bare skin
    dict(key='shoulder-kiss', name='He kisses her bare shoulder', aliases=['shoulder-kiss', 'kaandha'],
         mood='slow, sensual, deeply tender; aching soft love songs',
         scene='She wears a loose off-shoulder cream top that has slipped low, baring one shoulder '
               'completely. He wears an open navy button-down. From behind, he presses his lips to her '
               'bare shoulder; she is turned away, head tilted to the opposite side, eyes closed, one '
               'hand raised to his hand on her waist; her hair falls forward hiding her face.',
         framing=CLOSE),
    dict(key='bare-back', name='His hand on her bare back', aliases=['back', 'peeth'],
         mood='sensual, tender, slow burn; hushed intimate songs',
         scene='She wears a low-back crop top in charcoal, her back bare from shoulder to waist, hair '
               'swept to one side. He wears a loose grey linen shirt. He sits behind her, one open hand '
               'resting warm on the centre of her bare back — not pressing, just present; her head bows '
               'forward, eyes closed, the moment very still.',
         framing=CLOSE),
    dict(key='back-spine', name='He traces down her bare spine', aliases=['spine', 'rishta'],
         mood='slow sensuality, lost in each other; deep quiet love songs',
         scene='She stands facing away, wearing a backless satin top in dusty rose, her bare spine fully '
               'visible. He stands close behind in a plain white tee. He draws one hand slowly down her '
               'bare spine; her head tilts forward, eyes closed; her fingers reach back and rest on his '
               'wrist without stopping him.',
         framing=CLOSE),
    dict(key='undone', name='Her top slipped off both shoulders, he at her back', aliases=['undone', 'khula'],
         mood='deeply intimate, the whole world shut out; slow aching love songs',
         scene='She sits at the edge of a bed, back to the viewer, her loose off-shoulder top slipped '
               'off both shoulders — the full expanse of her bare back visible; she wears fitted high-waisted '
               'shorts. He sits just behind in an open white linen shirt, one hand resting at the nape of '
               'her neck, the other at the small of her back; warm lamp light from one side.',
         framing=CLOSE),
    dict(key='hip-trace', name='His hand on the curve of her hip', aliases=['hip', 'kamar'],
         mood='warm, skin-close, completely surrendered; slow night songs',
         scene='She lies on her side, wearing a minimal ribbed crop top, the waistband of cotton shorts '
               'low; the curve of her bare hip and the small of her back visible above the rumpled sheet. '
               'He lies behind her, hand resting lightly on that curve, arm around her; warm golden lamp '
               'light from behind.',
         framing=CLOSE),
    dict(key='hair-bury', name='He buries his face in her hair', aliases=['bury', 'baalon-mein'],
         mood='longing, inhaling her; deeply emotional tender songs',
         scene='She wears a loose oversized cream button-down shirt, bare-legged. He wears a plain grey '
               'tee. He holds her from behind, face pressed deep into her hair at the back of her head; '
               'her head leans back against him; both eyes closed; his hands hold her bare arms; warm '
               'side light.',
         framing=CLOSE),
    # ---------------------------------------------------------------- lying / tangled
    dict(key='lying-face', name='Lying facing each other, faces very close', aliases=['face-to-face', 'aamne-saamne'],
         mood='quiet intimacy, nothing needing to be said; slow acoustic songs',
         scene='Both in minimal sleepwear — she in a satin slip, he in a plain white tee. Lying on their '
               'sides facing each other, faces very close; one of his hands rests near her face almost '
               'touching her cheek; her hair falls between them and over her eyes; both still, the whole '
               'world just this space between them.',
         framing=CLOSE),
    dict(key='spoon', name='Spooning, his arm over her bare waist', aliases=['spoon', 'letna'],
         mood='safe, warm, deeply close; slow night love songs',
         scene='She wears only a thin ribbed crop top, bare-legged; he wears a plain white tee. He is '
               'curved tightly around her from behind — his arm over her bare waist, her hands holding '
               'his; her hair spills over both pillows, his face resting against the back of her neck; '
               'soft warm lamp light.',
         framing=FULL_SIT),
    dict(key='tangled-sleep', name='Tangled together, sheet half off', aliases=['tangled', 'uljhe'],
         mood='completely at peace with each other; lullaby-soft love songs',
         scene='Seen slightly from above: both asleep, deeply tangled — his arm across her bare waist, '
               'her leg over his; the sheet half-thrown off exposing arms, bare shoulders, and the curve '
               'of a bare back; she wears only a thin-strapped top, he is bare-chested; hair covering '
               'both faces; warm golden light at the frame edge.',
         framing=CLOSE),
    dict(key='lying-over-sleep', name='She sleeps, he watches her from beside', aliases=['watch', 'dekhna'],
         mood='adoring, peaceful, "I could watch you forever"; soft tender songs',
         scene='She lies asleep on her back wearing a satin slip, one bare shoulder and arm free, sheet '
               'draped loosely; he lies on his side beside her in a plain grey tee, head propped on one '
               'hand, watching her quietly; his other hand rests near her bare arm without touching; '
               'her hair spread across the pillow.',
         framing=CLOSE),
    # ---------------------------------------------------------------- kambal / blanket
    dict(key='kambal-cuddle', name='Bare under one blanket, curled into his chest', aliases=['kambal', 'cuddle'],
         mood='warm, skin-close, completely surrendered; slow night love songs',
         scene='Both under a thick rumpled blanket, bare shoulders and arms above the edge — she is '
               'clearly bare-shouldered, curled into his bare chest; her hair fans across him; a single '
               'warm lamp casting long soft shadows on the wall behind.',
         framing=FULL_SIT),
    dict(key='kambal-whisper', name='Under blanket, faces close, whispering', aliases=['kambal2', 'raat'],
         mood='private world, only us, late-night intimacy; soft confessional love songs',
         scene='Under a single blanket at night, both on their sides facing each other; bare shoulders '
               'just above the pulled-up edge; he whispers something, her lips curled in a small sleepy '
               'smile, hair tangled between them; the room dark except faint warm lamp glow.',
         framing=CLOSE),
    # ---------------------------------------------------------------- morning after
    dict(key='morning-after', name='Morning after — dishevelled, bare, still', aliases=['morning', 'subah'],
         mood='slow morning intimacy, wordless warmth; soft post-dawn love songs',
         scene='Soft dawn light through a window. She lies on her stomach asleep, bare from the waist up, '
               'the sheet pulled only to her lower back; one arm stretched across the pillow, her hair '
               'spread wide. He sits at the edge of the bed, bare-backed, one hand resting on her bare '
               'lower back, looking toward the window; rumpled sheets around them.',
         framing=FULL_SIT),
    dict(key='bare-morning', name='Morning, she in his shirt, he holds her', aliases=['morning2', 'subah2'],
         mood='slow morning intimacy, skin warm, unhurried; soft warm love songs',
         scene='Soft dawn light. She sits wearing only his oversized white linen shirt, mostly unbuttoned, '
               'bare legs and shoulders; he sits behind her, arms around her, face resting on her bare '
               'shoulder; both eyes closed, her hands holding his over her stomach; dust motes in the light.',
         framing=FULL_SIT),
    dict(key='bare-hug-sit', name='Her bare back against his bare chest, sitting', aliases=['barehug', 'khulna'],
         mood='completely safe, skin close, nothing hidden; emotional intimate songs',
         scene='She sits between his knees on the floor, her bare back against his bare chest — she wears '
               'only high-waisted cotton shorts; his arms wrap around her from behind, hands clasped at '
               'her stomach; her head tilts back onto his shoulder, hair falling away to one side; a '
               'loose sheet pools around them.',
         framing=FULL_SIT),
    dict(key='bare-window', name='Both bare-shouldered at a window, watching rain', aliases=['window', 'baarish'],
         mood='monsoon intimacy, cocooned from the world; baarish slow love songs',
         scene='Standing at an open window watching rain. She is bare-shouldered, back against his bare '
               'chest, his arms around her from behind; a thin sheet draped loosely over them both; '
               'rain streaks outside; warm lamp behind them, the rest of the room dark.',
         framing=FULL_SIT),
]

BY_KEY = {m['key']: m for m in MOMENTS}


def find(word):
    """Moment by key or alias (case-insensitive), else None."""
    w = (word or '').strip().lower()
    if not w:
        return None
    if w in BY_KEY:
        return BY_KEY[w]
    for m in MOMENTS:
        if w in m.get('aliases', []):
            return m
    return None


def recent_keys(history, n=None):
    keys = []
    for h in history or []:
        s = h.get('song', {}) if isinstance(h, dict) else {}
        if isinstance(s, dict) and s.get('moment'):
            keys.append(s['moment'])
    return keys if n is None else keys[-n:]


def pick(history, rng=None):
    """Least-recently-used moment, random among ties."""
    rng = rng or random.Random()
    used = recent_keys(history)
    last = {k: i for i, k in enumerate(used)}
    order = sorted(MOMENTS, key=lambda m: (last.get(m['key'], -1), rng.random()))
    return order[0]


def framing(m):
    return (m or {}).get('framing') or MID


def help_text():
    return '\n'.join(f"{m['aliases'][0] if m.get('aliases') else m['key']} - {m['name']}" for m in MOMENTS)
