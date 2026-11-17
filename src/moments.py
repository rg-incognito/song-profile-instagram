"""Couple 'moments' library: each reel picks one moment, then a song that fits its mood, then the image draws it.

Each moment: key, name, mood (what kind of song fits), scene (what to draw), framing (camera; default mid-shot),
aliases (words accepted by the Telegram bot: /reel spoon).
Rotation: least-recently-used first (from history.json), random among the unused ones.
All moments are intimate — close bodies, bare skin, tender or sensual.
"""
import random

MID = 'shown large as a mid shot (head-and-torso), cropped by the bottom edge of the image'
FULL_SIT = ('shown as a seated / low full-figure shot filling the lower 60-65% of the frame, bodies cropped by '
            'the bottom edge where needed')
CLOSE = 'a close, tender framing of the bodies (no faces needed), filling the lower 60-65% of the frame'

MOMENTS = [
    # ---------------------------------------------------------------- tender touch
    dict(key='hair-tuck', name='He tucks her hair behind her ear', aliases=['hair', 'zulf'],
         mood='soft, slow, admiring love; songs about her beauty, "tujhe dekha toh"',
         scene='Close together: he gently tucks a strand of her hair behind her ear with his fingers; her head '
               'is bowed shyly so her face stays hidden.'),
    dict(key='bindi', name='He fixes her bindi', aliases=['bindi'],
         mood='intimate, traditional, adoring love; soft devotional-romantic songs',
         scene='Face to face in profile, very close: he places a small red bindi on her forehead with his '
               'fingertip; her eyes are closed and hidden under her fringe.'),
    dict(key='forehead-kiss', name='Forehead kiss', aliases=['kiss', 'mathe'],
         mood='deep, safe, protective love; slow emotional love songs',
         scene='He holds her face gently and kisses her forehead; her eyes are closed and hidden under her hair, '
               'her hands holding his wrists.'),
    dict(key='jaw-cup', name='He cups her jaw, she leans into his hand', aliases=['jaw', 'rukhna'],
         mood='tender, adoring, deep devotion; slow emotional songs, "tujhe hi chahiye"',
         scene='Close and still: he cups the side of her face gently in one hand; she closes her eyes and '
               'leans into his palm, both hands holding his wrist; her hair falls over her eyes; a soft light '
               'catches the outline of their faces.',
         framing=CLOSE),
    dict(key='chin-tilt', name='He tilts her chin up gently', aliases=['chin', 'thaami'],
         mood='soft intensity, longing fulfilled; slow burn songs about finally being close',
         scene='He hooks one finger gently under her chin and tilts her face toward him; she lets him, eyes '
               'lowered and hidden, lips slightly parted; he looks at her with quiet intensity, his face in '
               'three-quarter profile.',
         framing=CLOSE),
    dict(key='fingers', name='Intertwined fingers', aliases=['hands', 'haath'],
         mood='promise, togetherness, intimate; slow emotional love songs',
         scene='Close focus on two hands intertwining fingers, her bangles and his watch, their sleeves and '
               'shoulders visible above.',
         framing=CLOSE),
    # ---------------------------------------------------------------- close embrace
    dict(key='backhug-him', name='He hugs her from behind', aliases=['backhug', 'peeche'],
         mood='safe, protective, soft love; slow romantic songs',
         scene='He hugs her from behind, arms wrapped around her waist, chin resting on top of her head; her '
               'hands rest on his arms, face tilted down and hidden.'),
    dict(key='tight-hug', name='Tight embrace, her face in his chest', aliases=['hug', 'milna'],
         mood='longing fulfilled, reunion, emotional love; intense romantic songs',
         scene='A tight embrace: she has her face buried deep in his chest, both hands clutching his shirt; '
               'his arms wrap fully around her, one hand cradling the back of her head; they stand very still, '
               'her hair spreading over his arms.',
         framing=CLOSE),
    dict(key='shirt-grip', name='She grips his shirt and pulls him closer', aliases=['grip', 'thaamo'],
         mood='longing, need, "don\'t go"; emotionally raw love songs',
         scene='She has both fists curled around the front of his shirt and pulls him toward her; he comes '
               'willingly, hand on the wall behind her; both faces close, hers turned down and hidden by hair, '
               'the moment urgent and quiet.',
         framing=CLOSE),
    dict(key='waist-pull', name='He gently pulls her close by the waist', aliases=['pull', 'kareeb'],
         mood='pull, longing, slow tension; deep aching romantic songs',
         scene='He reaches out and draws her toward him by the waist; she turns, surprised, one hand on his '
               'chest, their faces very close, both still; the world has gone quiet around them.',
         framing=CLOSE),
    # ---------------------------------------------------------------- slow dance / closeness
    dict(key='slow-dance', name='Slow dance, her forehead on his chest', aliases=['dance', 'naach'],
         mood='slow, intimate, waltz-like love; slow romantic ballads',
         scene='Slow dancing barefoot, her hands on his shoulders, his hands on her waist, her forehead '
               'resting against his chest; their eyes are closed, both completely surrendered to the moment.'),
    dict(key='wall-lean', name='He leans over her against a wall', aliases=['wall', 'deewar'],
         mood='tension, slow burn, intense closeness; deep longing romantic songs',
         scene='She stands with her back against a wall; he has one forearm raised against the wall above her, '
               'leaning in close; she looks down or to the side, one hand on his chest; they are almost touching, '
               'the air between them charged and still.',
         framing=CLOSE),
    dict(key='almost-kiss', name='Foreheads touching, almost a kiss', aliases=['almost', 'kareebi'],
         mood='tension, anticipation, deep longing; slow burn romantic songs',
         scene='Foreheads touching, eyes closed (hidden by hair), noses almost touching; his hand cups her jaw '
               'gently; both completely still, the moment just before.',
         framing=CLOSE),
    dict(key='nose-nuzzle', name='Nose nuzzle, breathing each other in', aliases=['nuzzle', 'saanson'],
         mood='quiet intimacy, completely lost in each other; breathy slow songs',
         scene='Noses just touching, eyes closed and hidden by hair, lips barely apart; his hand cradling the '
               'back of her head; her fingers curled in his shirt; both completely still, just breathing.',
         framing=CLOSE),
    # ---------------------------------------------------------------- whisper / ear
    dict(key='whisper', name='He whispers in her ear', aliases=['whisper', 'kaan'],
         mood='intimate, tender, longing; slow breathy love songs, "tere paas aana"',
         scene='He leans close, lips near her ear, whispering something; her head tilts toward him, eyes closed '
               'and hidden by her hair, a faint smile on her lips, his hand resting on her shoulder.'),
    # ---------------------------------------------------------------- bare skin
    dict(key='shoulder-kiss', name='He kisses her bare shoulder', aliases=['shoulder-kiss', 'kaandha'],
         mood='slow, sensual, deeply tender; aching soft love songs',
         scene='From behind, he presses his lips to her bare shoulder; she is turned slightly away, head tilted '
               'to the opposite side, eyes closed, one hand raised to touch his hand on her waist. Her hair '
               'falls forward, his face hidden by her hair and the angle.',
         framing=CLOSE),
    dict(key='bare-back', name='He rests his hand on her bare back', aliases=['back', 'peeth'],
         mood='sensual, tender, slow burn; hushed intimate songs, "yeh mera deewanapan"',
         scene='She sits with her back to him, bare skin visible from shoulder to waist; he sits behind her, '
               'one hand resting open on her bare upper back — not pressing, just present, warm; her head bows '
               'forward, hair falling over her face and shoulders.',
         framing=CLOSE),
    dict(key='back-spine', name='He traces her bare spine', aliases=['spine', 'rishta'],
         mood='slow sensuality, lost in each other; deep quiet love songs',
         scene='Standing close: she faces away, eyes closed, head slightly tilted — he draws one hand slowly '
               'down her bare spine from her shoulder blade down; her fingers reach back and touch his wrist '
               'without stopping him.',
         framing=CLOSE),
    dict(key='hair-bury', name='He buries his face in her hair', aliases=['bury', 'baalon-mein'],
         mood='longing, inhaling her, "can\'t get enough"; deeply emotional tender songs',
         scene='He holds her from behind, face pressed into her hair at the back of her head, eyes hidden; '
               'her head leans back against him; both eyes closed; his hands hold her arms gently; warm light '
               'from one side.',
         framing=CLOSE),
    # ---------------------------------------------------------------- lying / sleeping / blanket
    dict(key='lap-her', name='She sleeps on his lap', aliases=['lap', 'god'],
         mood='calm, sleepy, peaceful love; soft lullaby-like love songs',
         scene='She lies asleep with her head on his lap, curled up, hair spilling over his knees and covering '
               'her face; he sits leaning back, one hand resting in her hair, head bowed toward her.',
         framing=FULL_SIT),
    dict(key='lap-him', name='He sleeps on her lap, she plays with his hair', aliases=['lap2', 'sukoon'],
         mood='peaceful, sukoon, soft love; mellow indie love songs',
         scene='He lies with his head on her lap, eyes hidden in her dupatta; she sits cross-legged, fingers '
               'running through his hair, her face hidden behind her falling hair.',
         framing=FULL_SIT),
    dict(key='spoon', name='Spooning, lying together', aliases=['spoon', 'letna', 'paas'],
         mood='safe, warm, deeply close; slow night love songs, "tum saath ho"',
         scene='Lying on their side, he curved around her from behind — his arm over her waist, her hands '
               'holding his; her hair spills over both pillows, his face resting against the back of her head; '
               'soft dawn or lamp light on the wall.',
         framing=FULL_SIT),
    dict(key='lying-face', name='Lying facing each other, very close', aliases=['face-to-face', 'aamne-saamne'],
         mood='quiet intimacy, nothing needing to be said; slow acoustic songs',
         scene='Lying on their sides facing each other, faces very close but not touching; one of his hands '
               'rests near her face, almost touching her cheek; her hair falls between them and over her eyes; '
               'both still, the whole world just this space between them.',
         framing=CLOSE),
    dict(key='tangled-sleep', name='Tangled together under a blanket, sleeping', aliases=['tangled', 'uljhe'],
         mood='completely at peace with each other; lullaby-soft love songs',
         scene='Seen slightly from above: both asleep, deeply tangled — his arm across her bare waist, her '
               'leg over his, the blanket half-thrown off; only shoulders, arms, and the curve of a back '
               'visible; hair covering both faces; warm golden light at the edge of the frame.',
         framing=CLOSE),
    dict(key='blanket', name='Wrapped in one blanket together', aliases=['blanket', 'kambal'],
         mood='cozy, warm, rainy-night love; soft monsoon / winter love songs',
         scene='Both wrapped together in one thick blanket, she is tucked under his arm with her head on his '
               'chest, his hand resting in her hair; only their bare shoulders and faces (hidden) visible above '
               'the blanket edge.',
         framing=FULL_SIT),
    dict(key='kambal-cuddle', name='Cuddling bare under one blanket', aliases=['kambal2', 'cuddle'],
         mood='warm, skin-close, completely surrendered; slow night love songs, "tere bina"',
         scene='Both half-submerged under a thick rumpled blanket, only bare shoulders and arms above the edge; '
               'she is curled into his chest, his arm pulled tight around her bare shoulders; her hair fans '
               'across his chest; a single warm lamp light from one side casting long soft shadows.',
         framing=FULL_SIT),
    dict(key='kambal-whisper', name='Under blanket, faces close, whispering', aliases=['kambal3', 'raat2'],
         mood='private world, only us, late-night intimacy; soft confessional love songs',
         scene='Under a single blanket at night, both on their sides facing each other, faces very close; '
               'bare shoulders just visible above the pulled-up edge; he whispers something, her lips curled '
               'in a small sleepy smile, hair tangled between them; the room is dark except faint warm lamp glow.',
         framing=CLOSE),
    # ---------------------------------------------------------------- morning
    dict(key='bare-morning', name='Morning light, bare shoulders, he holds her', aliases=['morning', 'subah'],
         mood='slow morning intimacy, the world can wait; soft warm love songs',
         scene='Soft dawn light through a window; she sits wrapped loosely in a thin sheet, bare shoulders '
               'and collarbone visible; he sits behind her, arms around her, chin resting on her shoulder; '
               'both still, eyes closed, her hands holding his over her chest; dust motes in the light.',
         framing=FULL_SIT),
    dict(key='bare-hug-sit', name='Sitting embrace, her bare back against his chest', aliases=['barehug', 'khulna'],
         mood='completely safe, skin close, nothing hidden; emotional intimate songs',
         scene='She sits between his knees on the floor, bare back against his bare chest; his arms wrap around '
               'her from behind, hands clasped at her stomach; her head tilts back onto his shoulder, hair '
               'falling away to one side; a loose blanket pools around them.',
         framing=FULL_SIT),
    # ---------------------------------------------------------------- night / terrace
    dict(key='night-hold', name='Night embrace on the terrace', aliases=['raat', 'hold', 'aaghosh'],
         mood='quiet night love, holding tight, "tum ho toh"; late-night emotional songs',
         scene='On a dark terrace at night, she sits between his knees, back against his chest; his arms wrap '
               'fully around her from behind; her hands cover his; both still, faces hidden, city lights faint '
               'in the distance, a soft warm lamp nearby.',
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
