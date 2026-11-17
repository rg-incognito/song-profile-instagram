"""Couple 'moments' library: each reel picks one moment, then a song that fits its mood, then the image draws it.

Each moment: key, name, mood (what kind of song fits), scene (what to draw), framing (camera; default mid-shot),
aliases (words accepted by the Telegram bot: /reel wall).
Rotation: least-recently-used first (from history.json), random among the unused ones.
All moments are intimate / sensual. Clothing is contemporary Western, form-fitting and revealing.
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
         scene='She wears a fitted deep-V black crop top — neckline low, cleavage visible — and high-waisted '
               'fitted shorts that stop at mid-thigh. He wears a loose grey linen shirt, top buttons open. '
               'Foreheads touching, eyes closed and hidden by her hair, noses almost touching; his hand cups '
               'the side of her jaw gently; both completely still, the moment just before.',
         framing=CLOSE),
    dict(key='wall-lean', name='He leans over her against a wall', aliases=['wall', 'deewar'],
         mood='tension, slow burn, intense closeness; deep longing romantic songs',
         scene='She wears a thin-strapped cream slip dress cut high on the thigh — the hem at upper-thigh '
               'level, the neckline low enough to show cleavage. He wears a charcoal button-down, sleeves '
               'rolled. She stands with her back against a bare wall, one hand pressed flat on his chest; '
               'he leans in with one forearm raised against the wall, face angled down toward her neck; '
               'the air between them charged and completely still.',
         framing=CLOSE),
    dict(key='lying-over', name='He is propped over her on the bed', aliases=['over', 'upar'],
         mood='slow burn, suspended moment; deep aching love songs',
         scene='She lies on her back on rumpled white sheets wearing only a satin bralette and tiny cotton '
               'shorts, her legs bare from hip to foot; her hair spreads around her, face veiled by hair; '
               'he is propped over her, one hand beside her head, loose white shirt hanging fully open '
               'showing his chest; both completely still, faces very close.',
         framing=CLOSE),
    dict(key='nose-nuzzle', name='Noses touching, breathing each other in', aliases=['nuzzle', 'saanson'],
         mood='quiet intimacy, completely lost in each other; breathy slow songs',
         scene='She wears a loose oversized grey sweatshirt pulled far off one shoulder — one shoulder and '
               'the top of her chest exposed, bare thigh visible where the sweatshirt stops short. He wears '
               'a plain black tee. Noses just touching, eyes closed and hidden by her hair; his hand cradles '
               'the back of her head; her fingers curled into his shirt; both completely still.',
         framing=CLOSE),
    dict(key='chin-tilt', name='He tilts her chin up with one finger', aliases=['chin', 'thaami'],
         mood='soft intensity, longing fulfilled; slow burn romantic songs',
         scene='She wears a fitted low-cut sleeveless top in dusty rose — deep neckline, cleavage visible — '
               'and very short high-waisted shorts showing full thighs. He wears a dark olive linen shirt. '
               'He hooks one finger gently under her chin and tilts her face toward him; she lets him, eyes '
               'lowered and hidden by her fringe, the faint silhouette of slightly parted lips.',
         framing=CLOSE),
    dict(key='jaw-cup', name='He cups her jaw, she leans into his hand', aliases=['jaw', 'rukhna'],
         mood='tender, adoring, deep devotion; slow emotional songs',
         scene='She wears a low-cut off-shoulder black bodysuit, shoulders and chest exposed. He wears a '
               'cream linen button-down. Close and still: he cups the side of her face gently; she closes '
               'her eyes and leans into his palm completely, both hands holding his wrist; her hair falls '
               'forward over her eyes.',
         framing=CLOSE),
    # ---------------------------------------------------------------- pulling close
    dict(key='waist-pull', name='He pulls her close by the waist', aliases=['pull', 'kareeb'],
         mood='pull, longing, slow tension; deep aching romantic songs',
         scene='She wears a muted cream halter crop top — tied at the neck, back bare, cleavage showing — '
               'and tiny high-waisted shorts, full bare thighs and legs visible. He wears a dark grey linen '
               'shirt. He hooks his hand firmly around her bare waist and draws her toward him; she turns, '
               'one palm pressed flat on his chest, their faces very close, the faint silhouette of her '
               'parted lips, her long hair cascading forward veiling her eyes.',
         framing=CLOSE),
    dict(key='shirt-grip', name='She grips his shirt and pulls him closer', aliases=['grip', 'thaamo'],
         mood='longing, need, raw emotion; emotionally raw love songs',
         scene='She wears a thin-strapped olive slip dress with a deep V neckline and a high slit up one '
               'thigh — the thigh fully exposed through the slit. He wears a loose white linen shirt. She '
               'has both fists curled tight around the front of his shirt; he comes willingly, hand on the '
               'wall behind her; her face hidden by falling hair, the moment urgent and quiet.',
         framing=CLOSE),
    dict(key='strap-slip', name='He slides her strap off her shoulder', aliases=['strap', 'aanchal'],
         mood='slow, sensual, unhurried; hushed love songs',
         scene='She wears a thin-strapped satin slip dress in ivory — low-cut neckline with visible '
               'cleavage, hem at upper thigh. He wears a plain charcoal t-shirt. Standing close, he draws '
               'one thin strap slowly off her bare shoulder; it slips and bares her shoulder and more of '
               'her chest; she looks slightly to the side and down, one hand raised to rest on his; '
               'both still, the air very quiet.',
         framing=CLOSE),
    # ---------------------------------------------------------------- bare skin
    dict(key='shoulder-kiss', name='He kisses her bare shoulder', aliases=['shoulder-kiss', 'kaandha'],
         mood='slow, sensual, deeply tender; aching soft love songs',
         scene='She wears a low-cut bandeau crop top in black — strapless, showing cleavage and bare '
               'shoulders completely — and tiny shorts, bare thighs and legs fully visible. He wears an '
               'open navy button-down. From behind, he presses his lips to her bare shoulder; she is '
               'turned away, head tilted, eyes closed, one hand raised to touch his hand on her waist.',
         framing=CLOSE),
    dict(key='bare-back', name='His hand on her bare back', aliases=['back', 'peeth'],
         mood='sensual, tender, slow burn; hushed intimate songs',
         scene='She wears a low-cut backless crop top in charcoal — the entire back bare from shoulder '
               'to waist, the front neckline low showing cleavage. She wears high-cut cotton shorts, '
               'full bare thighs visible. He sits behind her, one open hand resting warm on the centre '
               'of her bare back; her head bows forward, eyes closed.',
         framing=CLOSE),
    dict(key='back-spine', name='He traces down her bare spine', aliases=['spine', 'rishta'],
         mood='slow sensuality, lost in each other; deep quiet love songs',
         scene='She stands facing away, wearing a backless satin halter in dusty rose — back fully bare '
               'from shoulders down, front showing deep cleavage — with high-cut shorts, bare thighs '
               'and legs completely visible. He stands close behind in a plain white tee. He draws one '
               'hand slowly down her bare spine; her head tilts forward, eyes closed; her fingers reach '
               'back and rest on his wrist without stopping him.',
         framing=CLOSE),
    dict(key='undone', name='Her top slipped off both shoulders, he at her back', aliases=['undone', 'khula'],
         mood='deeply intimate, the whole world shut out; slow aching love songs',
         scene='She sits at the edge of a bed, back to the viewer, her loose off-shoulder top slipped '
               'fully off both shoulders — the whole expanse of her bare back visible from shoulder to '
               'waist, bare legs stretched out in front of her. He sits just behind in an open white '
               'linen shirt, one hand at the nape of her neck, the other at the small of her back; '
               'warm lamp light from one side.',
         framing=CLOSE),
    dict(key='hip-trace', name='His hand on the curve of her hip', aliases=['hip', 'kamar'],
         mood='warm, skin-close, completely surrendered; slow night songs',
         scene='She lies on her side wearing only a minimal ribbed bralette; the waistband of her tiny '
               'shorts pushed very low, the full curve of her bare hip and the small of her back fully '
               'visible, bare thighs and legs extending from the frame. He lies behind her, hand resting '
               'on the curve of her hip, arm around her; warm golden lamp light.',
         framing=CLOSE),
    dict(key='hair-bury', name='He buries his face in her hair', aliases=['bury', 'baalon-mein'],
         mood='longing, inhaling her; deeply emotional tender songs',
         scene='She wears only a tiny low-cut crop top and extremely short shorts — bare shoulders, '
               'cleavage visible, full bare thighs and legs. He wears a plain grey tee. He holds her '
               'from behind, face pressed deep into her hair; her head leans back against him; both '
               'eyes closed; warm side light.',
         framing=CLOSE),
    # ---------------------------------------------------------------- lying / tangled
    dict(key='lying-face', name='Lying facing each other, faces very close', aliases=['face-to-face', 'aamne-saamne'],
         mood='quiet intimacy, nothing needing to be said; slow acoustic songs',
         scene='She wears a silky low-cut satin slip — neckline deep, cleavage visible, the hem riding '
               'very high on her bare thigh. He wears a plain white tee. Lying on their sides facing '
               'each other, faces very close; one of his hands rests near her cheek; her hair falls '
               'between them and over her eyes; both still.',
         framing=CLOSE),
    dict(key='spoon', name='Spooning, his arm over her bare waist', aliases=['spoon', 'letna'],
         mood='safe, warm, deeply close; slow night love songs',
         scene='She wears only a satin bralette — shoulders, chest and cleavage bare — with tiny shorts '
               'pushed low, bare waist and full bare thighs visible. He wears a plain white tee. He is '
               'curved tightly around her from behind, arm over her bare waist; her hair spills over '
               'both pillows; soft warm lamp light.',
         framing=FULL_SIT),
    dict(key='tangled-sleep', name='Tangled together, sheet half off', aliases=['tangled', 'uljhe'],
         mood='completely at peace with each other; lullaby-soft love songs',
         scene='Seen slightly from above: both asleep, deeply tangled. She wears only a satin bralette, '
               'bare from the waist up, her full bare thighs and legs visible — the sheet half-thrown off '
               'completely. He is bare-chested. His arm across her bare waist, her leg over his; hair '
               'covering both faces; warm golden light at the frame edge.',
         framing=CLOSE),
    dict(key='lying-over-sleep', name='She sleeps, he watches her from beside', aliases=['watch', 'dekhna'],
         mood='adoring, peaceful; soft tender songs',
         scene='She lies asleep on her back wearing only a low-cut satin bralette, bare from the waist '
               'up — cleavage visible, shoulders bare — with tiny shorts, bare thighs and long bare '
               'legs stretched across the bed; a sheet draped only over her lower legs. He lies on his '
               'side beside her in a plain grey tee, head propped on one hand, watching her quietly.',
         framing=CLOSE),
    # ---------------------------------------------------------------- kambal / blanket
    dict(key='kambal-cuddle', name='Bare under one blanket, curled into his chest', aliases=['kambal', 'cuddle'],
         mood='warm, skin-close, completely surrendered; slow night love songs',
         scene='Both under a thick rumpled blanket — clearly bare beneath it. Only her bare shoulders, '
               'the top of her chest and cleavage, and his bare chest and arms are visible above the '
               'blanket edge. She is curled into his bare chest, his arm pulled tight around her; her '
               'hair fans across him; a single warm lamp.',
         framing=FULL_SIT),
    dict(key='kambal-whisper', name='Under blanket, faces close, whispering', aliases=['kambal2', 'raat'],
         mood='private world, only us, late-night intimacy; soft confessional love songs',
         scene='Under a single blanket at night, both on their sides facing each other — bare shoulders '
               'and the top of her chest visible above the blanket edge, clearly bare beneath; he '
               'whispers something, her lips curled in a small sleepy smile, hair tangled between them; '
               'the room dark except faint warm lamp glow.',
         framing=CLOSE),
    # ---------------------------------------------------------------- morning after
    dict(key='morning-after', name='Morning after — dishevelled, bare, still', aliases=['morning', 'subah'],
         mood='slow morning intimacy, wordless warmth; soft post-dawn love songs',
         scene='Soft dawn light through a window. She lies on her stomach asleep, completely bare from '
               'shoulder to lower back — the sheet pulled only across her hips and upper thighs; her '
               'bare back, shoulders and the side of her chest visible; one arm stretched across the '
               'pillow, her hair spread wide. He sits at the edge of the bed, bare-backed, one hand '
               'resting on her bare lower back looking toward the window.',
         framing=FULL_SIT),
    dict(key='bare-morning', name='Morning, she in his shirt, he holds her', aliases=['morning2', 'subah2'],
         mood='slow morning intimacy, skin warm, unhurried; soft warm love songs',
         scene='Soft dawn light. She wears only his oversized white linen shirt — fully unbuttoned and '
               'hanging open, showing her bare chest and cleavage, bare waist, and bare thighs; nothing '
               'underneath. He sits behind her, bare-chested, arms around her, face resting on her bare '
               'shoulder; both eyes closed.',
         framing=FULL_SIT),
    dict(key='bare-hug-sit', name='Her bare back against his bare chest, sitting', aliases=['barehug', 'khulna'],
         mood='completely safe, skin close, nothing hidden; emotional intimate songs',
         scene='She sits between his knees on the floor wearing only a tiny bralette and very short '
               'shorts — her bare back against his bare chest, bare waist and full bare thighs and '
               'legs stretched out in front. His arms wrap around her from behind, hands clasped at '
               'her stomach; her head tilts back onto his shoulder, hair falling away; a loose sheet '
               'pools around them.',
         framing=FULL_SIT),
    dict(key='bare-window', name='Both bare-shouldered at a window, watching rain', aliases=['window', 'baarish'],
         mood='monsoon intimacy, cocooned from the world; baarish slow love songs',
         scene='Standing at an open window watching rain. She wears only a low-cut satin bralette — '
               'bare shoulders, cleavage fully visible, bare waist and thighs — his arms around her '
               'from behind, his bare chest against her bare back; a thin sheet draped loosely across '
               'their lower halves only; rain streaks outside; warm lamp behind them.',
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
