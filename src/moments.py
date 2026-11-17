"""Couple 'moments' library: each reel picks one moment, then a song that fits its mood, then the image draws it.

Each moment: key, name, mood (what kind of song fits), scene (what to draw), framing (camera; default mid-shot),
aliases (words accepted by the Telegram bot: /reel spoon).
Rotation: least-recently-used first (from history.json), random among the unused ones.
All moments are intimate / sensual — close bodies, bare skin, charged stillness.
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
         scene='Foreheads touching, eyes closed (hidden by hair), noses almost touching; his hand cups her jaw '
               'gently; both completely still, the moment just before.',
         framing=CLOSE),
    dict(key='nose-nuzzle', name='Nose nuzzle, breathing each other in', aliases=['nuzzle', 'saanson'],
         mood='quiet intimacy, completely lost in each other; breathy slow songs',
         scene='Noses just touching, eyes closed and hidden by hair, lips barely apart; his hand cradling the '
               'back of her head; her fingers curled in his shirt; both completely still, just breathing.',
         framing=CLOSE),
    dict(key='wall-lean', name='He leans over her against a wall', aliases=['wall', 'deewar'],
         mood='tension, slow burn, intense closeness; deep longing romantic songs',
         scene='She stands with her back against a wall; he has one forearm raised against the wall above her, '
               'leaning in close, face near her neck; she looks to the side, one hand pressed flat on his '
               'chest; they are barely not touching, the air between them charged and still.',
         framing=CLOSE),
    dict(key='lying-over', name='He is propped over her on the bed', aliases=['over', 'upar'],
         mood='slow burn, suspended moment, completely absorbed; deep aching love songs',
         scene='She lies on her back on a bed, hair spread around her, face turned slightly to the side and '
               'hidden by hair; he is propped over her, one hand beside her head on the pillow, the other '
               'resting near her waist; their faces are very close; both completely still, the moment held.',
         framing=CLOSE),
    dict(key='chin-tilt', name='He tilts her chin up gently', aliases=['chin', 'thaami'],
         mood='soft intensity, longing fulfilled; slow burn songs about finally being close',
         scene='He hooks one finger gently under her chin and tilts her face toward him; she lets him, eyes '
               'lowered and hidden, lips slightly parted; he looks at her with quiet intensity, his face in '
               'three-quarter profile.',
         framing=CLOSE),
    dict(key='jaw-cup', name='He cups her jaw, she leans into his hand', aliases=['jaw', 'rukhna'],
         mood='tender, adoring, deep devotion; slow emotional songs',
         scene='Close and still: he cups the side of her face gently in one hand; she closes her eyes and '
               'leans into his palm, both hands holding his wrist; her hair falls over her eyes; a soft light '
               'catches the outline of their faces.',
         framing=CLOSE),
    # ---------------------------------------------------------------- pulling close
    dict(key='waist-pull', name='He pulls her close by the waist', aliases=['pull', 'kareeb'],
         mood='pull, longing, slow tension; deep aching romantic songs',
         scene='He reaches out and draws her toward him by the waist; she turns, surprised, one hand pressed '
               'flat on his chest, their faces very close; both still, her lips slightly parted.',
         framing=CLOSE),
    dict(key='shirt-grip', name='She grips his shirt and pulls him closer', aliases=['grip', 'thaamo'],
         mood='longing, need, "don\'t go"; emotionally raw love songs',
         scene='She has both fists curled around the front of his shirt and pulls him toward her; he comes '
               'willingly, hand on the wall behind her; both faces close, hers turned down and hidden by hair, '
               'the moment urgent and quiet.',
         framing=CLOSE),
    dict(key='dupatta-slip', name='He slides her dupatta off her shoulder', aliases=['dupatta', 'aanchal'],
         mood='slow, sensual, unhurried; hushed love songs, "yeh jo halka halka"',
         scene='Standing close, he draws her dupatta slowly off one shoulder with his fingertips; it slips '
               'and pools softly at their feet, baring her shoulder; she looks slightly to the side and down, '
               'one hand raised to rest on his; both still, the air very quiet.',
         framing=CLOSE),
    # ---------------------------------------------------------------- bare skin / touch
    dict(key='shoulder-kiss', name='He kisses her bare shoulder', aliases=['shoulder-kiss', 'kaandha'],
         mood='slow, sensual, deeply tender; aching soft love songs',
         scene='From behind, he presses his lips to her bare shoulder; she is turned away, head tilted to the '
               'opposite side, eyes closed, one hand raised to touch his hand on her waist; her hair falls '
               'forward hiding her face.',
         framing=CLOSE),
    dict(key='bare-back', name='He rests his hand on her bare back', aliases=['back', 'peeth'],
         mood='sensual, tender, slow burn; hushed intimate songs',
         scene='She sits with her bare back to him, hair pinned up leaving her back fully exposed; he sits '
               'just behind her, one open hand resting warm on her bare upper back; her head bows forward '
               'slightly, eyes closed.',
         framing=CLOSE),
    dict(key='back-spine', name='He traces down her bare spine', aliases=['spine', 'rishta'],
         mood='slow sensuality, lost in each other; deep quiet love songs',
         scene='Standing close, she faces away — he draws one hand slowly down her bare spine from shoulder '
               'blade to the small of her back; her head tilts forward, eyes closed; her fingers reach back '
               'and rest on his wrist without stopping him.',
         framing=CLOSE),
    dict(key='undone', name='Her blouse open at the back, he touches her spine', aliases=['undone', 'khula'],
         mood='deeply intimate, the whole world shut out; slow aching love songs',
         scene='She sits at the edge of a bed, back to the viewer, her blouse loosened and slipped off both '
               'shoulders — the full expanse of her bare back visible; he sits just behind her, one hand '
               'resting at the base of her neck, the other at the small of her back; both still and quiet, '
               'warm lamp light from one side.',
         framing=CLOSE),
    dict(key='hip-trace', name='His hand on the curve of her hip under the blanket', aliases=['hip', 'kamar'],
         mood='warm, skin-close, completely surrendered; slow night songs',
         scene='Seen from slightly above: she lies on her side, back to him; the blanket pulled low revealing '
               'the curve of her bare hip and the small of her back; his hand rests lightly on that curve, '
               'arm around her; warm golden lamp light from behind.',
         framing=CLOSE),
    dict(key='hair-bury', name='He buries his face in her hair', aliases=['bury', 'baalon-mein'],
         mood='longing, inhaling her; deeply emotional tender songs',
         scene='He holds her from behind, face pressed into her hair at the back of her head; her head leans '
               'back against him; both eyes closed; his hands hold her bare arms; warm light from one side.',
         framing=CLOSE),
    # ---------------------------------------------------------------- lying / tangled
    dict(key='lying-face', name='Lying facing each other, faces very close', aliases=['face-to-face', 'aamne-saamne'],
         mood='quiet intimacy, nothing needing to be said; slow acoustic songs',
         scene='Lying on their sides facing each other, faces very close; one of his hands rests near her '
               'face, almost touching her cheek; her hair falls between them and over her eyes; both still, '
               'the whole world just this space between them.',
         framing=CLOSE),
    dict(key='spoon', name='Spooning, his arm over her bare waist', aliases=['spoon', 'letna'],
         mood='safe, warm, deeply close; slow night love songs',
         scene='Lying on their side, he curved tightly around her from behind — his arm over her bare waist, '
               'her hands holding his; her hair spills over both pillows; his face resting against the back '
               'of her neck; soft lamp light.',
         framing=FULL_SIT),
    dict(key='tangled-sleep', name='Tangled together, blanket half off', aliases=['tangled', 'uljhe'],
         mood='completely at peace with each other; lullaby-soft love songs',
         scene='Seen from slightly above: both asleep, deeply tangled — his arm across her bare waist, her '
               'leg over his; the blanket half-thrown off exposing arms, shoulders, and the curve of a bare '
               'back; hair covering both faces; warm golden light at the frame edge.',
         framing=CLOSE),
    dict(key='lying-over-sleep', name='She sleeps, he watches her from beside', aliases=['watch', 'dekhna'],
         mood='adoring, peaceful, "I could watch you forever"; soft tender songs',
         scene='She lies asleep on her back, sheet draped loosely, one bare shoulder and arm free; he lies '
               'on his side beside her, head propped on one hand, watching her quietly; his other hand rests '
               'near her bare arm without touching; her hair spread across the pillow.',
         framing=CLOSE),
    # ---------------------------------------------------------------- kambal / blanket
    dict(key='kambal-cuddle', name='Bare under one blanket, curled into his chest', aliases=['kambal', 'cuddle'],
         mood='warm, skin-close, completely surrendered; slow night love songs',
         scene='Both under a thick rumpled blanket, only bare shoulders and arms above the edge; she is '
               'curled into his chest, his arm pulled tight around her bare shoulders; her hair fans across '
               'his chest; a single warm lamp casting long soft shadows.',
         framing=FULL_SIT),
    dict(key='kambal-whisper', name='Under blanket, faces close, whispering in the dark', aliases=['kambal2', 'raat'],
         mood='private world, only us, late-night intimacy; soft confessional love songs',
         scene='Under a single blanket at night, both on their sides facing each other, faces very close; '
               'bare shoulders just visible above the pulled-up edge; he whispers something, her lips curled '
               'in a small sleepy smile, hair tangled between them; the room dark except faint warm lamp glow.',
         framing=CLOSE),
    # ---------------------------------------------------------------- morning after
    dict(key='morning-after', name='Morning after — dishevelled, bare, still', aliases=['morning', 'subah'],
         mood='slow morning intimacy, wordless warmth, the world can wait; soft post-dawn love songs',
         scene='Soft dawn light through a window; she lies on her stomach asleep, sheet pulled to just below '
               'her bare waist, one arm stretched across the pillow; he sits at the edge of the bed, bare '
               'back to the viewer, one hand resting on her bare lower back, looking toward the window; '
               'rumpled pillows, her hair spread wide.',
         framing=FULL_SIT),
    dict(key='bare-morning', name='Morning, she wrapped in a sheet, he holds her', aliases=['morning2', 'subah2'],
         mood='slow morning intimacy, skin warm, unhurried; soft warm love songs',
         scene='Soft dawn light; she sits wrapped loosely in a thin sheet, bare shoulders and collarbone '
               'fully visible; he sits behind her, arms wrapped around her, face resting on her bare '
               'shoulder; both eyes closed, her hands holding his over her chest; dust motes in the light.',
         framing=FULL_SIT),
    dict(key='bare-hug-sit', name='Her bare back against his bare chest, sitting', aliases=['barehug', 'khulna'],
         mood='completely safe, skin close, nothing hidden; emotional intimate songs',
         scene='She sits between his knees on the floor or bed, her bare back against his bare chest; his '
               'arms wrap around her from behind, hands clasped at her stomach; her head tilts back onto '
               'his shoulder, hair falling away to one side; a loose sheet pools around them.',
         framing=FULL_SIT),
    dict(key='bare-window', name='Both bare-shouldered at a window, watching rain', aliases=['window', 'baarish'],
         mood='monsoon intimacy, cocooned from the world; baarish slow love songs',
         scene='Standing close at an open window watching rain; she is bare-shouldered, back against his '
               'chest, his arms around her from behind; a thin sheet draped loosely over them both; rain '
               'streaks outside; warm lamp behind them.',
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
