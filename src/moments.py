"""Couple 'moments' library: each reel picks one moment, then a song that fits its mood, then the image draws it.

Each moment: key, name, mood (what kind of song fits), scene (what to draw), framing (camera; default mid-shot),
aliases (words accepted by the Telegram bot: /reel wall).
Rotation: least-recently-used first (from history.json), random among ties.
All moments are tender / emotional — safe for Instagram recommendations, high completion rate, shareable.
"""
import random

MID = 'shown large as a mid shot (head-and-torso), cropped by the bottom edge of the image'
FULL_SIT = ('shown as a seated / low full-figure shot filling the lower 60-65% of the frame, bodies cropped by '
            'the bottom edge where needed')
CLOSE = 'a close, tender framing of the bodies (no faces needed), filling the lower 60-65% of the frame'

MOMENTS = [
    dict(key='forehead-kiss', name='He kisses her forehead', aliases=['forehead', 'maatha'],
         tier='tender',
         mood='tender, protective, devoted; emotional slow songs',
         scene='She wears a soft dusty-rose dupatta pinned loosely over her head, one wisp of hair across '
               'her cheek. He wears a simple white kurta. He tilts forward and presses his lips gently to '
               'her forehead; she closes her eyes, the smallest smile; warm golden light from one side.',
         framing=MID),
    dict(key='morning-chai', name='Morning chai together', aliases=['chai', 'subah-chai'],
         tier='tender',
         mood='warm, candid morning intimacy; cozy soft songs',
         scene='She wears an oversized pastel lavender tee that slips off one shoulder, loose cotton shorts. '
               'He wears a plain grey tee. Both sit cross-legged on a bed, two clay chai mugs between them; '
               'she leans her cheek on his shoulder, both eyes half-closed; warm morning light through thin '
               'curtains.',
         framing=MID),
    dict(key='earphones', name='Sharing one pair of earphones', aliases=['earphones', 'gaana'],
         tier='tender',
         mood='shared world, quietly close; acoustic indie songs',
         scene='He wears a white linen shirt with the sleeves pushed up. She wears a soft olive tee. They '
               'sit side by side on the floor, one earbud each; a phone on the floor between them; she '
               'leans her head on his shoulder, eyes closed; a small smile on both their faces.',
         framing=MID),
    dict(key='backhug', name='She hugs him from behind', aliases=['backhug', 'peechhe-se'],
         tier='tender',
         mood='playful warmth, missing him; affectionate indie songs',
         scene='He stands near a window in a loose blue button-down, sleeves rolled up, looking out. She '
               'wears a cream cropped tee and high-waisted jeans. She slips her arms around him from behind, '
               'cheek pressed into his back; he covers her hands with one of his; warm afternoon light.',
         framing=MID),
    dict(key='rain-watch', name='Watching rain from a window', aliases=['rain', 'baarish-dekhna'],
         tier='tender',
         mood='cozy, monsoon warmth, two people in their own world; baarish romantic songs',
         scene='They stand together at a wide window watching steady rain; she wears an oversized knit '
               'sweater and leggings, he wears a loose grey tee and track trousers. His arm is around her '
               'shoulders; she leans into him, one hand on the glass; rain streaks the pane; a steaming '
               'mug on the sill.',
         framing=MID),
    dict(key='reading', name='Reading together on a lazy afternoon', aliases=['reading', 'kitaab'],
         tier='tender',
         mood='peaceful companionship, unhurried; quiet acoustic songs',
         scene='She lies across a sofa, feet in his lap, reading a paperback; she wears soft floral '
               'pyjamas. He sits at the other end in a plain tee, one hand resting on her ankle, '
               'his own book open but forgotten; afternoon light pools across both of them.',
         framing=MID),
    dict(key='shy-blush', name='She blushes, he notices', aliases=['blush', 'sharmana'],
         tier='tender',
         mood='shy, sweet, blushing first-love; playful soft romantic songs',
         scene='She wears a soft yellow salwar kameez with tiny embroidery at the neckline, a thin dupatta. '
               'He wears a dark blue kurta. She looks down with a helpless smile, cheeks visibly warm; '
               'he tilts his head to try to catch her eye, one corner of his mouth lifted; warm diffused '
               'afternoon light.',
         framing=MID),
    dict(key='umbrella', name='Under one umbrella in the rain', aliases=['umbrella', 'chhaata'],
         tier='tender',
         mood='soft, monsoon romance, tender closeness; baarish romantic songs',
         scene='Standing close under a single small umbrella in heavy rain; she wears a '
               'white kurta that has gone slightly damp at the edges, he wears a navy shirt. His '
               'arm around her keeps the umbrella slightly more toward her; she looks up at him; '
               'rain pours all around, warm street lamp glow.',
         framing=MID),
    dict(key='walk-away', name='Walking away together, hand in hand', aliases=['walk', 'saath-chalein'],
         tier='tender',
         mood='tender journey, forever together; soul acoustic songs',
         scene='Seen from behind: they walk down a quiet lane, hand in hand. She wears a '
               'flowing mustard anarkali, he wears a plain white kurta. Their silhouettes fill '
               'the lower frame, the road stretches ahead into soft golden haze.',
         framing=MID),
    dict(key='cycle', name='Cycling together on a bright afternoon', aliases=['cycle', 'cycle-ride'],
         tier='tender',
         mood='breezy, free-spirited, innocent love; cheerful acoustic songs',
         scene='She sits on the crossbar of his bicycle, bare feet dangling. She wears a floral '
               'midi dress in dusty pink; he wears a sky-blue tee and chinos. He pedals slowly, '
               'face close to hers; both laughing; sunlit road, trees dappling light.',
         framing=MID),
    dict(key='bindi', name='He puts her bindi on for her', aliases=['bindi', 'maang'],
         tier='tender',
         mood='devotional, tender, intimate ritual; soulful traditional songs',
         scene='She sits before a small mirror on a stool, wearing a simple cotton sari in '
               'muted teal, hair loosely braided. He stands behind her, leaning forward, '
               'carefully pressing a small bindi between her brows; her eyes are half-closed, '
               'a soft smile; warm oil-lamp light.',
         framing=MID),
    dict(key='cant-sleep', name='3 AM — can\'t sleep, thinking of you', aliases=['cant-sleep', '3am'],
         tier='tender',
         mood='sleepless longing, 3am restlessness; dreamy late-night songs',
         scene='She sits up in bed, knees pulled to her chest, staring at her phone screen in '
               'the dark; she wears a soft off-shoulder night dress in pale grey. He texts back '
               'in another room: a warm lamp glow. Both lit only by their screens; the room '
               'otherwise dark.',
         framing=MID),
    dict(key='video-call', name='Late-night video call', aliases=['video-call', 'facetime'],
         tier='tender',
         mood='long-distance longing, tender separation; bittersweet romantic songs',
         scene='She lies on her stomach in bed propped on her elbows, phone in both hands, '
               'talking to him on a video call; she wears a soft tee. His face glows on her '
               'screen. The room is dark except the phone light on her face; she is smiling '
               'and sleepy.',
         framing=MID),
    dict(key='cooking', name='Cooking together, stealing glances', aliases=['cooking', 'khana'],
         tier='tender',
         mood='domestic warmth, playful love; cheerful cozy songs',
         scene='A small warm kitchen, afternoon light. She stirs something at the stove in a '
               'loose cotton kurti; he stands beside her, sneaking a taste from the pot, earning '
               'a mock-scolding look. Both laughing. Warm turmeric tones, the kitchen cluttered '
               'and lived-in.',
         framing=MID),
    dict(key='letter', name='Writing a letter, lost in thought', aliases=['letter', 'khat'],
         tier='tender',
         mood='longing, old-world romance, written love; poetic soulful songs',
         scene='She sits at a wooden desk by a window, writing a handwritten letter. She wears '
               'a soft cotton kurti, her dupatta draped loosely. A dried rose petal on the paper. '
               'She pauses with the pen to her lips, looking out the window; diffused afternoon '
               'light.',
         framing=MID),
    dict(key='fingers', name='Their fingers interlaced, close-up', aliases=['fingers', 'haath'],
         tier='tender',
         mood='promise, togetherness, holding on; tender devotional songs',
         scene='A very close shot: their two hands, fingers woven together, resting on a soft '
               'surface. Her bangles (glass, blue and gold) catch the light. His fingers are '
               'steady around hers. The rest of them is a soft blur behind.',
         framing=CLOSE),
    dict(key='doodle', name='She doodles on his arm while he sleeps', aliases=['doodle', 'likha'],
         tier='tender',
         mood='playful, tender, adoring quiet love; light acoustic songs',
         scene='He sleeps on the sofa, head turned away; he wears a plain white tee. She sits '
               'cross-legged beside him in a soft tee and pyjamas, drawing small flowers on his '
               'forearm with a marker; a tiny amused smile on her face; afternoon light.',
         framing=MID),
    dict(key='haldi', name='Haldi ceremony — she smears haldi on his cheek', aliases=['haldi', 'pithi'],
         tier='tender',
         mood='playful traditional joy, pre-wedding warmth; festive romantic songs',
         scene='She wears a bright yellow lehenga choli, haldi-stained. He wears a simple '
               'ivory kurta. She leans forward and smears haldi on his cheek with her finger; '
               'he pretends to protest, both laughing; marigold garlands in the background.',
         framing=MID),
    dict(key='scooter', name='Evening scooter ride together', aliases=['scooter', 'scooty'],
         tier='tender',
         mood='free, breezy, urban romance; indie road-trip songs',
         scene='She rides pillion, arms around him, head against his back; she wears a '
               'kurta in cobalt blue, dupatta streaming in the wind; he wears a plain '
               'grey tee and jeans. City lights behind them, dusk sky pink-orange.',
         framing=MID),
    dict(key='mirror-ready', name='She gets ready, he watches in the mirror', aliases=['mirror', 'aaina'],
         tier='tender',
         mood='adoring, quietly watching, proud love; soft emotional songs',
         scene='She stands before a mirror pinning her dupatta, wearing a simple silk salwar '
               'kameez in sage green. He leans in the doorway behind her, watching her in '
               'the reflection with a quiet fond expression; she catches his eye in the '
               'mirror and smiles.',
         framing=MID),
    dict(key='rooftop-night', name='Rooftop night, city lights below', aliases=['rooftop', 'chhath'],
         tier='tender',
         mood='dreamy, atmospheric, city romance; night-time indie songs',
         scene='They sit on the edge of a rooftop at night, feet dangling; she wears a soft '
               'kurta in deep plum, he wears a black tee. City lights glow below and around '
               'them. His arm behind her; she leans slightly toward him; a loose string of '
               'fairy lights behind them.',
         framing=MID),
    dict(key='fairy-lights', name='Fairy lights, sitting close', aliases=['lights', 'twinkling'],
         tier='tender',
         mood='magical, dreamy, cozy closeness; dreamy acoustic songs',
         scene='They sit close on a low bed or mat surrounded by fairy lights strung in '
               'loose loops; she wears a soft white salwar, he wears a loose linen shirt. '
               'The lights cast a warm glow on their faces; she tilts her head toward him; '
               'both quiet and content.',
         framing=MID),
    dict(key='photo', name='She shows him an old photo, both smiling', aliases=['photo', 'tasveer'],
         tier='tender',
         mood='nostalgic, warm memory, shared history; bittersweet love songs',
         scene='They sit together on a floor, an old photo album between them; she points '
               'at something, laughing. She wears a casual cotton kurta in dusty orange; '
               'he wears a white tee. Warm afternoon light; dust motes in the air.',
         framing=MID),
    dict(key='coat', name='He puts his coat on her shoulders', aliases=['coat', 'jacket'],
         tier='tender',
         mood='protective, chivalrous, winter love; cold-day tender songs',
         scene='Evening, mild chill. She shivers slightly in a simple salwar kameez. He '
               'takes off his dark woollen jacket and settles it over her shoulders from '
               'behind; she pulls it closer around herself and looks up at him; streetlight '
               'behind them.',
         framing=MID),
    dict(key='fight-sulk', name='She sulks, he coaxes', aliases=['sulk', 'sulkana'],
         tier='tender',
         mood='playful sulk, sweet coaxing, light-hearted; breezy love songs',
         scene='She sits with her back to him, arms crossed, pretending to ignore him. She '
               'wears a simple churidar in soft terracotta. He sits in front of her, hands '
               'folded in mock apology, pulling a ridiculous sorry face. She is clearly '
               'fighting a smile.',
         framing=MID),
    dict(key='fight-chai', name='Making up over a cup of chai', aliases=['fight-chai', 'manana'],
         tier='tender',
         mood='sweet making-up, cozy forgiveness; gentle emotional songs',
         scene='Aftermath of a small fight. She sits at the kitchen table in a simple kurti, '
               'arms still crossed slightly. He sets a steaming chai in front of her without a '
               'word and sits across; she looks at the chai, then at him; both on the edge of '
               'forgiving.',
         framing=MID),
    dict(key='alta', name='He paints alta on her feet', aliases=['alta', 'payal-alta'],
         tier='tender',
         mood='devotional, intimate ritual, sacred love; traditional soulful songs',
         scene='He kneels before her and carefully paints alta (red lac dye) on the soles '
               'of her feet with a small brush. She wears a beautiful silk lehenga in '
               'deep maroon; her feet are bare; he is absorbed in the careful work; a '
               'warm oil-lamp on the floor beside them.',
         framing=CLOSE),
    dict(key='mehendi-name', name='His name hidden in her mehendi', aliases=['mehendi', 'mehndi'],
         tier='tender',
         mood='playful, traditional wedding joy; festive bridal songs',
         scene='She holds her hand out, fresh mehendi still drying; the design is elaborate. '
               'He kneels, face close, searching her palm for his name hidden in the pattern; '
               'both smiling. She wears a yellow-green lehenga; he wears an ivory kurta; warm '
               'lamp light.',
         framing=CLOSE),
    dict(key='varmala', name='Varmala — garlands exchanged', aliases=['varmala', 'shaadi'],
         tier='tender',
         mood='emotional wedding promise, tender, joyful tears; shaadi emotional songs',
         scene='Elevated view: she raises a garland of marigolds toward him; he bows slightly '
               'to let her reach. She wears a heavy red bridal lehenga; he wears a sherwani '
               'in cream and gold. Marigold petals shower around them; flower-lit mandap behind.',
         framing=MID),
    dict(key='sindoor', name='He puts sindoor in her maang', aliases=['sindoor', 'maang-tikka'],
         tier='tender',
         mood='sacred devotion, life-promise; deeply emotional traditional songs',
         scene='Intimate close-shot: she sits very still, eyes lowered, wearing a '
               'shimmering red bridal dupatta. He stands before her, lifting a pinch of '
               'vermilion carefully toward the parting of her hair; both completely still; '
               'warm lamp and marigold glow.',
         framing=CLOSE),
    dict(key='saree-pleats', name='He carefully tucks her saree pleats', aliases=['saree', 'pallu'],
         tier='tender',
         mood='domestic devotion, careful tenderness; soulful songs',
         scene='She stands in a soft cotton saree in muted teal, one hand raised lightly '
               'on his shoulder for balance. He kneels at her feet, tucking the pleats into '
               'place carefully; both quiet; warm morning light through a half-open window.',
         framing=MID),
    dict(key='hair-braid', name='He braids her hair slowly', aliases=['braid', 'choti'],
         tier='tender',
         mood='slow tender domesticity, being taken care of; soft acoustic songs',
         scene='She sits on the floor in front of him, eyes closed, clearly relaxed. She '
               'wears a simple cotton kurti; he sits behind, carefully braiding her long '
               'hair, a small look of concentration on his face; afternoon light.',
         framing=MID),
    dict(key='hair-tuck', name='He tucks a strand of hair behind her ear', aliases=['hair-tuck', 'baalon-mein'],
         tier='tender',
         mood='softly adoring, paying quiet attention; tender romantic songs',
         scene='She wears a simple mustard dupatta that has slipped over her hair; a loose '
               'strand falls across her face. He reaches over and tucks it back gently behind '
               'her ear, his finger just grazing her cheek; she looks up at him, surprised by '
               'the tenderness.',
         framing=MID),
    dict(key='lap-her', name='She rests her head in his lap', aliases=['lap', 'god-mein'],
         tier='tender',
         mood='safe, peaceful, completely at ease; soft lullaby-like love songs',
         scene='She lies with her head in his lap on a sofa; she wears a soft dusty-rose '
               'tee and leggings. He wears a plain white kurta. He reads a book above her, '
               'one hand resting absently on her hair; she is half-asleep; warm afternoon '
               'light.',
         framing=MID),
    dict(key='sleep-shoulder', name='She sleeps on his shoulder on a train/bus', aliases=['sleep-shoulder', 'kaandhe-pe-sona'],
         tier='tender',
         mood='travel, quiet closeness, comfortable love; breezy travel songs',
         scene='They sit together on a train window seat; she has fallen asleep against '
               'his shoulder. She wears a soft kurti in dusty pink; he wears a plain blue '
               'shirt. He looks out the moving window, carefully still so he doesn\'t wake '
               'her; golden field outside.',
         framing=MID),
    dict(key='window-wait', name='She waits by the window for him', aliases=['wait', 'intezaar'],
         tier='tender',
         mood='longing, tender anticipation; yearning romantic songs',
         scene='She stands at a tall window, one hand on the glass, looking out at a '
               'rain-washed street. She wears a soft muted green salwar; a dupatta slips '
               'off her shoulder. The room behind is dim; the light outside is grey and '
               'diffused; a lone lamp on the sill.',
         framing=MID),
    dict(key='beach', name='Bare feet, walking at the water\'s edge', aliases=['beach', 'samundar'],
         tier='tender',
         mood='free, breezy, endless romantic horizon; breezy summer love songs',
         scene='Sunset. They walk at the edge of the sea, water lapping over bare feet. '
               'She wears a loose sundress in white, hem damp; he wears linen trousers '
               'rolled to the knee. Their hands swing loosely between them; the horizon '
               'is gold and coral.',
         framing=MID),
    dict(key='run-to-him', name='She runs to him — reunion', aliases=['run', 'milo'],
         tier='tender',
         mood='joyful reunion, euphoric love, running heart; breezy feel-good songs',
         scene='A wide shot: she runs toward him across a sunlit courtyard or station '
               'platform, arms wide; she wears a flowing yellow anarkali. He opens his '
               'arms, face lit up. The light is golden and generous.',
         framing=MID),
    dict(key='fight-backtoback', name='Back to back, not speaking but still together', aliases=['backtoback', 'naraaz'],
         tier='tender',
         mood='sweet sulking, quiet naraazgi; bittersweet emotional songs',
         scene='They sit back-to-back on a bed, both arms crossed, not looking at each '
               'other — but their backs are still touching. She wears a simple cotton '
               'tee; he wears a plain kurta. Both trying to look annoyed; the tension '
               'between them is half-serious.',
         framing=MID),
    dict(key='fight-pillow', name='Pillow fight', aliases=['pillow', 'takiya'],
         tier='tender',
         mood='playful, carefree, laughing love; breezy playful songs',
         scene='She holds a pillow above her head, mid-swing, laughing. He ducks, also '
               'laughing, one arm raised to block. Both in casual home clothes — she in '
               'a pastel oversized tee; he in a simple tee and shorts. White sheets '
               'everywhere. Afternoon light.',
         framing=MID),
    dict(key='rain-dance', name='Dancing in the rain', aliases=['rain-dance', 'baarish-mein-naachna'],
         tier='tender',
         mood='carefree joy, monsoon abandon; baarish joyful songs',
         scene='Heavy rain. She spins with arms out in the downpour, completely drenched, '
               'laughing; she wears a soft white kurta and leggings. He stands a step away '
               'watching her with the most helplessly fond expression. Rain blurs everything '
               'around them.',
         framing=MID),
    dict(key='payal', name='He puts her payal on for her', aliases=['payal', 'anklet'],
         tier='tender',
         mood='devotional, tender, intimate ritual; soulful traditional songs',
         scene='He kneels before her, carefully fastening a silver payal around her ankle. '
               'She wears a soft silk lehenga in sage green; her bare foot rests on his knee. '
               'He is absorbed in the clasp; she watches him from above with quiet warmth; '
               'golden light.',
         framing=CLOSE),
    dict(key='backhug-him', name='He hugs her from behind while she works', aliases=['backhug-him', 'andar-se'],
         tier='tender',
         mood='warm surprise, spontaneous love; sweet domestic songs',
         scene='She stands at a desk or kitchen counter, busy; she wears a loose kurti in '
               'powder blue. He comes up behind her and wraps his arms around her without '
               'warning, chin on her shoulder; she stops mid-task, her hands covering his, '
               'eyes closing; a quiet morning.',
         framing=MID),
    dict(key='dilli-ki-baarish', name='Watching the city rain from a tea stall', aliases=['dilli', 'tea-stall'],
         tier='tender',
         mood='cozy urban monsoon, chai and rain; Dilli baarish songs',
         scene='A small roadside tea stall; they sit on a wooden bench under a tarpaulin, '
               'cups of chai, watching rain sheet down the street. She wears a simple '
               'dupatta over a kurta in mustard; he wears a navy sweatshirt. Both quiet, '
               'shoulders touching, steam rising from the cups.',
         framing=MID),
    dict(key='guitar', name='He plays guitar for her', aliases=['guitar', 'gaana-bajaana'],
         tier='tender',
         mood='sweet acoustic serenade, old-school romance; acoustic folk songs',
         scene='Evening. He sits on the floor, guitar in hand, playing something quiet; '
               'he wears a soft grey kurta. She sits across from him, knees drawn up, '
               'listening with her chin in her hand and a small smile; warm lamp and '
               'twilight from the window.',
         framing=MID),
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
