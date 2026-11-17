"""Couple 'moments' library: each reel picks one moment, then a song that fits its mood, then the image draws it.

Each moment: key, name, mood (what kind of song fits), scene (what to draw), framing (camera; default mid-shot),
aliases (words accepted by the Telegram bot: /reel payal).
Rotation: least-recently-used first (from history.json), random among the unused ones.
"""
import random

MID = 'shown large as a mid shot (head-and-torso), cropped by the bottom edge of the image'
FULL_SIT = ('shown as a seated / low full-figure shot filling the lower 60-65% of the frame, bodies cropped by '
            'the bottom edge where needed')
CLOSE = 'a close, tender framing of the bodies (no faces needed), filling the lower 60-65% of the frame'

# intimate=True: preferred when the feed is biased toward intimacy (picked ~2× more often)

MOMENTS = [
    # ---------------------------------------------------------------- nok-jhok / little fights
    dict(key='fight-sulk', name='Little fight - she sulks, he tries to make up', aliases=['fight', 'nokjhok', 'jhagda'],
         mood='playful, cute, teasing love; manana / making-up / "don\'t be angry" songs',
         scene='She sits with arms crossed and her back half-turned to him, chin up, sulking. He leans toward her '
               'from behind her shoulder holding out a single flower (or a small chocolate) as a peace offering. '
               'Cute and light, not angry.'),
    dict(key='fight-backtoback', name='Little fight - sitting back to back', aliases=['backtoback', 'naraz'],
         mood='sweet sulking, missing each other while angry, cute tension; songs about naraazgi / manana',
         scene='They sit back to back on the floor after a small fight, both with arms crossed, heads turned '
               'slightly away; but their little fingers are secretly hooked together on the floor between them.',
         framing=FULL_SIT),
    dict(key='fight-cheekpoke', name='Making up - he pokes her pouting cheek', aliases=['poke', 'manana'],
         mood='playful, teasing, flirty; light-hearted romantic songs',
         scene='She is pouting and turned away in profile (eyes hidden by hair); he grins and gently pokes her '
               'puffed cheek with one finger from the side, trying to make her smile.'),
    dict(key='fight-chai', name='Making up with a cup of chai', aliases=['chai', 'sorry'],
         mood='warm, apologetic, sweet; songs about sorry, care, "tum ho toh"',
         scene='She sits sulking on a low stool, looking away; he crouches in front of her, holding up a small '
               'clay kulhad of chai with both hands like an apology, head tilted.',
         framing=FULL_SIT),
    dict(key='fight-pillow', name='Pillow fight that ends in laughter', aliases=['pillow'],
         mood='fun, carefree, laughing love; upbeat-soft romantic songs',
         scene='Mid pillow fight on a bed: she swings a pillow at him, hair flying over her face; he shields '
               'himself with one arm, laughing, feathers drifting in the air.'),
    # ---------------------------------------------------------------- tender care
    dict(key='payal', name='He puts a payal on her ankle', aliases=['feet', 'anklet', 'pairon'],
         mood='tender, devoted, shy love; songs about devotion, "tera hone laga hoon", worship-like love',
         scene='She sits on the edge of a low wooden bed or step, one foot resting on his knee; he sits on the '
               'floor in front of her, carefully fastening a silver payal (anklet with tiny bells) around her '
               'ankle with both hands. She looks down at him shyly, hair falling over her face. Her feet have '
               'light red alta on the edges.',
         framing=FULL_SIT),
    dict(key='alta', name='He paints alta on her feet', aliases=['mehendi'],
         mood='devoted, traditional, intimate love; soft classical-touch romantic songs',
         scene='He kneels and paints red alta along the edge of her foot with a thin brush; she sits above him '
               'holding the hem of her saree, watching, face hidden by hair.',
         framing=FULL_SIT),
    dict(key='hair-tuck', name='He tucks her hair behind her ear', aliases=['hair', 'zulf'],
         mood='soft, slow, admiring love; songs about her beauty, "tujhe dekha toh"',
         scene='Close together: he gently tucks a strand of her hair behind her ear with his fingers; her head '
               'is bowed shyly so her face stays hidden.', intimate=True),
    dict(key='hair-braid', name='He braids her hair', aliases=['braid', 'choti'],
         mood='gentle, everyday, homely love; calm acoustic love songs',
         scene='She sits on the floor between his knees; he sits behind her on a chair, clumsily but carefully '
               'braiding her long dark hair, a hair tie between his teeth.',
         framing=FULL_SIT),
    dict(key='bindi', name='He fixes her bindi', aliases=['bindi'],
         mood='intimate, traditional, adoring love; soft devotional-romantic songs',
         scene='Face to face in profile, very close: he places a small red bindi on her forehead with his '
               'fingertip; her eyes are closed and hidden under her fringe.', intimate=True),
    dict(key='feeding', name='Feeding each other', aliases=['food', 'khana'],
         mood='cute, caring, playful love; light romantic songs',
         scene='Sitting cross-legged facing each other, he feeds her a bite with his hand while she leans in, '
               'hair covering her eyes; a simple steel thali between them.',
         framing=FULL_SIT),
    dict(key='forehead-kiss', name='Forehead kiss', aliases=['kiss', 'mathe'],
         mood='deep, safe, protective love; slow emotional love songs',
         scene='He holds her face gently and kisses her forehead; her eyes are closed and hidden under her hair, '
               'her hands holding his wrists.', intimate=True),
    dict(key='coat', name='He puts his jacket on her shoulders', aliases=['jacket', 'thand'],
         mood='protective, caring love on a cold night; soft winter love songs',
         scene='From slightly behind, he drapes his oversized jacket over her shoulders; she pulls it close '
               'around herself, head tilted toward him.'),
    # ---------------------------------------------------------------- sleepy / resting
    dict(key='lap-her', name='She sleeps on his lap', aliases=['lap', 'god'],
         mood='calm, sleepy, peaceful love; soft lullaby-like love songs',
         scene='She lies asleep with her head on his lap, curled up, hair spilling over his knees and covering '
               'her face; he sits leaning back, one hand resting in her hair, head bowed toward her.',
         framing=FULL_SIT, intimate=True),
    dict(key='lap-him', name='He sleeps on her lap, she plays with his hair', aliases=['lap2', 'sukoon'],
         mood='peaceful, sukoon, soft love; mellow indie love songs',
         scene='He lies with his head on her lap, eyes hidden in her dupatta; she sits cross-legged, fingers '
               'running through his hair, her face hidden behind her falling hair.',
         framing=FULL_SIT, intimate=True),
    dict(key='sleep-shoulder', name='Asleep on his shoulder on a train', aliases=['train', 'safar'],
         mood='travel, quiet togetherness, dreamy love; journey love songs',
         scene='Side by side on a train berth / bench, she has fallen asleep on his shoulder; he sits very still '
               'so she does not wake, sharing one earphone with her.'),
    dict(key='blanket', name='Wrapped in one blanket', aliases=['blanket', 'kambal'],
         mood='cozy, warm, rainy-night love; soft monsoon / winter love songs',
         scene='Both wrapped together in one thick blanket on the floor, she is tucked under his arm with her '
               'head on his chest, two mugs of tea beside them.',
         framing=FULL_SIT, intimate=True),
    # ---------------------------------------------------------------- hugs
    dict(key='backhug-her', name='She hugs him from behind, cheek on his shoulder', aliases=['backhug', 'shoulder'],
         mood='warm, affectionate, "you are mine" love; cute romantic songs',
         scene='She hugs him from behind, arms around his chest, her cheek resting on his shoulder with her hair '
               'covering her eyes; he holds her hands on his chest and smiles in profile.'),
    dict(key='backhug-him', name='He hugs her from behind', aliases=['backhug2'],
         mood='safe, protective, soft love; slow romantic songs',
         scene='He hugs her from behind, arms wrapped around her waist, chin resting on top of her head; her '
               'hands rest on his arms, face tilted down and hidden.', intimate=True),
    dict(key='tight-hug', name='Tight hug after missing each other', aliases=['hug', 'milna'],
         mood='longing fulfilled, reunion, emotional love; intense romantic songs',
         scene='A tight reunion hug: she has run into his arms, her face buried in his chest, his arms wrapped '
               'fully around her, a dropped bag at their feet.'),
    dict(key='piggyback', name='Piggyback ride', aliases=['piggy'],
         mood='fun, carefree, childlike love; happy romantic songs',
         scene='She rides piggyback on him, arms around his neck, laughing with her head thrown back and hair '
               'over her face; he holds her legs and leans forward.'),
    dict(key='shoulder-sit', name='Head on his shoulder, sitting side by side', aliases=['kandha'],
         mood='quiet, content, companionship; soft slow love songs',
         scene='Sitting side by side on a terrace ledge, she rests her head on his shoulder; his head leans '
               'on top of hers; their hands are intertwined between them.'),
    # ---------------------------------------------------------------- outings & places
    dict(key='umbrella', name='Sharing one umbrella in the rain', aliases=['rain', 'baarish'],
         mood='monsoon romance, rain love; baarish songs',
         scene='Standing close under one black umbrella in light rain, he tilts it toward her so his own '
               'shoulder gets wet; she holds his arm.'),
    dict(key='rain-dance', name='Dancing in the rain', aliases=['dance-rain'],
         mood='joyful monsoon love; upbeat-soft rain songs',
         scene='Dancing barefoot in the rain, he spins her by one hand, her dupatta and wet hair swinging and '
               'hiding her face, rain streaks drawn as simple lines.'),
    dict(key='scooter', name='Scooter ride, her arms around him', aliases=['bike', 'ride'],
         mood='free, breezy, road-trip love; feel-good love songs',
         scene='On a vintage scooter, he drives, she sits behind with her arms around his waist and her cheek '
               'on his back, dupatta flying in the wind.'),
    dict(key='earphones', name='Sharing earphones', aliases=['music', 'earphone'],
         mood='indie, dreamy, "this song is us"; soft indie love songs',
         scene='Sitting close on a bench, sharing one pair of wired earphones, her head on his shoulder, both '
               'looking down at one phone between them.'),
    dict(key='slow-dance', name='Slow dance in the kitchen', aliases=['dance'],
         mood='slow, intimate, waltz-like love; slow romantic ballads',
         scene='Slow dancing barefoot in a simple kitchen, her hands on his shoulders, his hands on her waist, '
               'her forehead against his chest.', intimate=True),
    dict(key='stargazing', name='Lying on the terrace, stargazing', aliases=['stars', 'taare'],
         mood='dreamy, night-time, wishful love; night love songs',
         scene='Lying on a terrace mat seen from above, heads touching, pointing at the sky, hair covering '
               'their faces, a few tiny stars drawn above them.',
         framing=CLOSE),
    dict(key='cycle', name='She sits on his cycle bar', aliases=['cycle'],
         mood='nostalgic, innocent, first-love; old-school / 90s love songs',
         scene='She sits sideways on the front bar of his bicycle, he pedals with his chin near her shoulder, '
               'her hair blowing over both their faces.'),
    dict(key='terrace-kite', name='Flying a kite on the terrace', aliases=['kite', 'patang'],
         mood='sunny, playful, innocent love; cheerful soft love songs',
         scene='On a terrace, he holds the kite string while she stands in front of him holding the reel, '
               'his arms around her guiding her hands, both looking up.'),
    dict(key='beach', name='Walking at the beach', aliases=['sea', 'samandar'],
         mood='breezy, free, endless love; dreamy love songs',
         scene='Walking barefoot along the water, she holds her sandals in one hand and his hand in the other, '
               'seen from three-quarter back, wind in her hair.'),
    dict(key='walk-away', name='Walking away holding hands', aliases=['walk', 'saath'],
         mood='forever, journey together, promise; songs about "saath"',
         scene='Seen from behind, they walk away side by side holding hands, her head leaning toward his '
               'shoulder.'),
    # ---------------------------------------------------------------- longing / waiting
    dict(key='window-wait', name='Waiting at the window', aliases=['wait', 'intezaar'],
         mood='longing, waiting, missing someone; yearning love songs',
         scene='She leans on a window frame, chin on her folded arms, looking out (face hidden by hair); his '
               'reflection is faintly drawn in the glass beside her.'),
    dict(key='video-call', name='Long distance video call', aliases=['call', 'distance', 'doori'],
         mood='long-distance love, missing each other; doori / virah love songs',
         scene='Split composition: on the left she lies on her bed hugging a pillow holding a phone, on the right '
               'he sits at a desk holding a phone, both phones glowing softly toward each other.'),
    dict(key='letter', name='Reading his letter', aliases=['letter', 'khat'],
         mood='nostalgic, longing, old-school love; classic soft love songs',
         scene='She sits on the floor holding a handwritten letter to her chest, eyes closed and hidden by her '
               'hair; a few dried rose petals around her.',
         framing=FULL_SIT),
    # ---------------------------------------------------------------- shaadi / devotion
    dict(key='haldi', name='Haldi - putting haldi on her cheek', aliases=['haldi', 'shaadi'],
         mood='wedding joy, playful-traditional love; shaadi love songs',
         scene='In yellow clothes, he smears a little haldi on her cheek with two fingers while she laughs and '
               'turns away, marigold petals in the air.'),
    dict(key='varmala', name='Varmala moment', aliases=['wedding', 'varmala'],
         mood='wedding, forever promise, emotional love; wedding love ballads',
         scene='She, in a red lehenga with a dupatta over her head, places a marigold varmala around his neck; '
               'he bows his head toward her, both faces hidden.'),
    dict(key='sindoor', name='He fills her sindoor', aliases=['sindoor'],
         mood='sacred, devoted, forever love; devotional-romantic songs',
         scene='He gently fills sindoor in her hair parting with his fingertip; her eyes are lowered and hidden '
               'under her red dupatta, her hands folded at her chest.'),
    dict(key='saree-pleats', name='He fixes her saree pleats', aliases=['saree'],
         mood='homely, caring, shy love; soft romantic songs',
         scene='He kneels and holds the pleats of her saree straight while she tucks them in, looking down at '
               'him shyly with hair covering her face.',
         framing=FULL_SIT),
    dict(key='mehendi-name', name='Searching his name in her mehendi', aliases=['naam'],
         mood='shy, playful wedding love; cute shaadi songs',
         scene='She holds out her mehendi-covered hands; he leans in close, searching for his hidden name in the '
               'design, his finger tracing her palm.'),
    # ---------------------------------------------------------------- everyday cute
    dict(key='cooking', name='Cooking together', aliases=['kitchen', 'cook'],
         mood='homely, playful, everyday love; light romantic songs',
         scene='In a small kitchen, she rolls rotis while he hugs her from behind and steals a bite of something '
               'from the pan, flour on her cheek.'),
    dict(key='guitar', name='He plays guitar for her', aliases=['guitar', 'gaana'],
         mood='serenade, indie, sweet love; acoustic indie love songs',
         scene='He sits on the floor playing an acoustic guitar, singing toward her; she sits beside him hugging '
               'her knees, head resting on her knees and tilted toward him.',
         framing=FULL_SIT),
    dict(key='photo', name='He photographs her', aliases=['camera', 'photo'],
         mood='admiring, "you are my favourite view"; songs about her beauty',
         scene='He holds an old film camera up to his face (face hidden by the camera) photographing her; she '
               'turns away shyly, hand half covering her face.'),
    dict(key='reading', name='Reading together', aliases=['book', 'kitab'],
         mood='calm, intellectual, soft love; mellow indie songs',
         scene='Sitting on the floor against a bed, she reads a book while leaning on his chest; he reads over '
               'her shoulder with his chin on her head.',
         framing=FULL_SIT),
    dict(key='cheek-pinch', name='She pinches his cheeks', aliases=['cute'],
         mood='cute, teasing, bubbly love; cheerful romantic songs',
         scene='She stands on tiptoes and pinches both his cheeks while he pretends to be annoyed, head tilted, '
               'her hair hiding her face.'),
    dict(key='shy-blush', name='She hides her face in her hands, he smiles', aliases=['shy', 'sharmana'],
         mood='shy, blushing, first-love; sweet love songs',
         scene='She hides her blushing face in both hands; he stands close, gently trying to pull her hands '
               'away, smiling in profile.'),
    dict(key='fingers', name='Intertwined fingers', aliases=['hands', 'haath'],
         mood='promise, togetherness, intimate; slow emotional love songs',
         scene='Close focus on two hands intertwining fingers, her bangles and his watch, their sleeves and '
               'shoulders visible above.',
         framing=CLOSE, intimate=True),
    # ---------------------------------------------------------------- late night / phone
    dict(key='late-night-text', name='Late night texting, phone glow', aliases=['text', 'raat', 'phone'],
         mood='late-night longing, thinking of you; slow night love songs',
         scene='She lies on her stomach in bed late at night, chin resting on her arms, holding her phone '
               'close to her face — a soft blue-white glow lights her from below; outside the window a dark '
               'night sky; she is smiling at the screen, hair falling over her shoulder.',
         framing=FULL_SIT),
    dict(key='cant-sleep', name='Both awake at 3am, video call', aliases=['3am', 'neend'],
         mood='can\'t sleep without you; dreamy insomniac love songs',
         scene='Split panel: on the left she sits in dark with knees pulled to chest, phone held up; '
               'on the right he lies on his back holding his phone up to the ceiling, both bathed in '
               'phone-screen glow, smiling.'),
    # ---------------------------------------------------------------- rainy window together
    dict(key='rain-window-together', name='Both watching rain from a window', aliases=['barishwindow', 'monsoon'],
         mood='monsoon together, cozy rain love; baarish / sawan love songs',
         scene='They stand close at an open window watching rain; she leans on his shoulder, one hand resting '
               'on the window sill; rain streaks outside; a warm lamp glow behind them.',
         framing=FULL_SIT),
    # ---------------------------------------------------------------- morning
    dict(key='morning-chai', name='Morning chai in bed', aliases=['morning', 'subah'],
         mood='everyday warmth, domestic love; soft morning love songs',
         scene='She sits cross-legged on the bed, eyes half-open, hair messy; he sits beside her handing her '
               'a steaming kulhad of chai with both hands, sunlight stripe through a window on the wall behind.',
         framing=FULL_SIT),
    dict(key='sleep-wakeup', name='He wakes her up gently', aliases=['wakeup', 'uth'],
         mood='tender, sleepy, morning love; soft gentle love songs',
         scene='She is asleep, face hidden in a pillow; he sits on the edge of the bed, gently nudging her '
               'shoulder, holding a cup of tea, early morning light slanting across the bed.',
         framing=FULL_SIT),
    # ---------------------------------------------------------------- rooftop / night sky
    dict(key='rooftop-night', name='Rooftop at night, city lights below', aliases=['rooftop', 'chhatt'],
         mood='dreamy night love, city romance; night-sky romantic songs',
         scene='Sitting on a rooftop parapet at night, feet dangling, distant city lights and stars; she leans '
               'her head on his shoulder, a string of fairy lights strung above them.',
         framing=FULL_SIT),
    dict(key='fairy-lights', name='Under fairy lights on a terrace', aliases=['lights', 'diya'],
         mood='warm, festive, magical love; dreamy soft love songs',
         scene='Standing close under a string of warm fairy lights draped across a terrace; she holds the '
               'light string up to look at it, he watches her face glowing in the light, her other hand in his.',
         framing=FULL_SIT),
    # ---------------------------------------------------------------- catching / running
    dict(key='almost-fall', name='She slips and he catches her', aliases=['catch', 'sambhalna'],
         mood='protective, reflex love, "I will always catch you"; warm romantic songs',
         scene='She slipped on a wet step; he caught her, one arm around her waist, her hand gripping his '
               'shirt; she looks up in surprise, face hidden by hair falling across it.',
         framing=FULL_SIT),
    dict(key='run-to-him', name='She runs and jumps into his arms', aliases=['jump', 'milne-dauda'],
         mood='reunion, excitement, overjoyed love; upbeat joyful love songs',
         scene='She runs toward him, arms out; he opens his arms wide, slightly crouched to catch her; '
               'hair and dupatta flying behind her, leaves scattered underfoot.',
         framing=FULL_SIT),
    # ---------------------------------------------------------------- mirror / getting ready
    dict(key='mirror-ready', name='He watches her get ready at the mirror', aliases=['mirror', 'taiyaar'],
         mood='admiring, "you are beautiful without trying"; songs about her beauty',
         scene='She stands at a mirror fixing her earring, unaware; he leans in the doorway behind her, '
               'watching her reflection with a soft smile, her reflection showing her face hidden by hair.',
         framing=FULL_SIT),
    # ---------------------------------------------------------------- study / work
    dict(key='study-care', name='She studies, he brings her food', aliases=['study', 'padhai'],
         mood='silent care, supportive love; mellow indie songs about home',
         scene='She sits at a desk late, books and notes spread out, bent over work; he quietly sets a plate '
               'of food and a glass of water beside her, she looks up surprised, hair falling over her face.',
         framing=FULL_SIT),
    # ---------------------------------------------------------------- almost-kiss
    dict(key='almost-kiss', name='Foreheads touching, almost a kiss', aliases=['almost', 'kareebi'],
         mood='tension, anticipation, deep longing; slow burn romantic songs',
         scene='Foreheads touching, eyes closed (hidden by hair), noses almost touching; his hand cups her jaw '
               'gently; both completely still, the moment just before.',
         framing=CLOSE, intimate=True),
    # ---------------------------------------------------------------- intimate / close
    dict(key='whisper', name='He whispers in her ear', aliases=['whisper', 'kaan'],
         mood='intimate, tender, longing; slow breathy love songs, "tere paas aana"',
         scene='He leans close, lips near her ear, whispering something; her head tilts toward him, eyes closed '
               'and hidden by her hair, a faint smile on her lips, his hand resting on her shoulder.',
         intimate=True),
    dict(key='waist-pull', name='He gently pulls her close by the waist', aliases=['pull', 'kareeb'],
         mood='pull, longing, slow tension; deep aching romantic songs',
         scene='He reaches out and draws her toward him by the waist; she turns, surprised, one hand on his '
               'chest, their faces very close, both still; the world has gone quiet around them.',
         framing=CLOSE, intimate=True),
    dict(key='night-hold', name='Night embrace on the terrace', aliases=['raat', 'hold', 'aaghosh'],
         mood='quiet night love, holding tight, "tum ho toh"; late-night emotional songs',
         scene='On a dark terrace at night, she sits between his knees, back against his chest; his arms wrap '
               'fully around her from behind; her hands cover his; both still, faces hidden, city lights faint '
               'in the distance, a soft warm lamp nearby.',
         framing=FULL_SIT, intimate=True),
    dict(key='shoulder-kiss', name='He kisses her bare shoulder', aliases=['shoulder-kiss', 'kaandha'],
         mood='slow, sensual, deeply tender; aching soft love songs',
         scene='From behind, he presses his lips to her bare shoulder; she is turned slightly away, head tilted '
               'to the opposite side, eyes closed, one hand raised to touch his hand on her waist. Her hair '
               'falls forward, his face hidden by her hair and the angle.',
         framing=CLOSE, intimate=True),
    dict(key='wall-lean', name='He leans over her against a wall', aliases=['wall', 'deewar'],
         mood='tension, slow burn, intense closeness; deep longing romantic songs',
         scene='She stands with her back against a wall; he has one forearm raised against the wall above her, '
               'leaning in close; she looks down or to the side, one hand on his chest; they are almost touching, '
               'the air between them charged and still.',
         framing=CLOSE, intimate=True),
    dict(key='spoon', name='Spooning, lying together', aliases=['spoon', 'letna', 'paas'],
         mood='safe, warm, deeply close; slow night love songs, "tum saath ho"',
         scene='Lying on their side, he curved around her from behind — his arm over her waist, her hands '
               'holding his; her hair spills over both pillows, his face resting against the back of her head; '
               'soft dawn or lamp light on the wall.',
         framing=FULL_SIT, intimate=True),
    dict(key='jaw-cup', name='He cups her jaw, she leans into his hand', aliases=['jaw', 'rukhna'],
         mood='tender, adoring, deep devotion; slow emotional songs, "tujhe hi chahiye"',
         scene='Close and still: he cups the side of her face gently in one hand; she closes her eyes and '
               'leans into his palm, both hands holding his wrist; her hair falls over her eyes; a soft light '
               'catches the outline of their faces.',
         framing=CLOSE, intimate=True),
    dict(key='nose-nuzzle', name='Nose nuzzle, breathing each other in', aliases=['nuzzle', 'saanson'],
         mood='quiet intimacy, completely lost in each other; breathy slow songs',
         scene='Noses just touching, eyes closed and hidden by hair, lips barely apart; his hand cradling the '
               'back of her head; her fingers curled in his shirt; both completely still, just breathing.',
         framing=CLOSE, intimate=True),
    dict(key='chin-tilt', name='He tilts her chin up gently', aliases=['chin', 'thaami'],
         mood='soft intensity, longing fulfilled; slow burn songs about finally being close',
         scene='He hooks one finger gently under her chin and tilts her face toward him; she lets him, eyes '
               'lowered and hidden, lips slightly parted; he looks at her with quiet intensity, his face in '
               'three-quarter profile.',
         framing=CLOSE, intimate=True),
    dict(key='shirt-grip', name='She grips his shirt and pulls him closer', aliases=['grip', 'thaamo'],
         mood='longing, need, "don\'t go"; emotionally raw love songs',
         scene='She has both fists curled around the front of his shirt and pulls him toward her; he comes '
               'willingly, hand on the wall behind her; both faces close, hers turned down and hidden by hair, '
               'the moment urgent and quiet.',
         framing=CLOSE, intimate=True),
    dict(key='hair-bury', name='He buries his face in her hair', aliases=['bury', 'baalon-mein'],
         mood='longing, inhaling her, "can\'t get enough"; deeply emotional tender songs',
         scene='He holds her from behind, face pressed into her hair at the back of her head, eyes hidden; '
               'her head leans back against him; both eyes closed; his hands hold her arms gently; warm light '
               'from one side.',
         framing=CLOSE, intimate=True),
    dict(key='shirt-chest', name='She hides her face in his chest, gripping his shirt', aliases=['chest', 'seena'],
         mood='overwhelming emotion, safe refuge; songs about finally breaking down with someone',
         scene='She has buried her face deep in his chest, both hands clutching his shirt; he wraps both arms '
               'tight around her, one hand cradling the back of her head; they stand very still, her hair '
               'spreading over his arms.',
         framing=CLOSE, intimate=True),
    dict(key='lying-face', name='Lying facing each other, very close', aliases=['face-to-face', 'aamne-saamne'],
         mood='quiet intimacy, nothing needing to be said; slow acoustic songs',
         scene='Lying on their sides facing each other, faces very close but not touching; one of his hands '
               'rests near her face, almost touching her cheek; her hair falls between them and over her eyes; '
               'both still, the whole world just this space between them.',
         framing=CLOSE, intimate=True),
    # ---------------------------------------------------------------- doodling
    dict(key='doodle', name='She doodles on his hand', aliases=['doodle', 'likhai'],
         mood='playful, bored-together love; light indie acoustic songs',
         scene='She sits beside him, holding his hand in her lap and drawing small doodles (hearts, stars, '
               'his name) on his palm with a pen; he watches her, chin resting on her head.',
         framing=CLOSE),
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
    """Least-recently-used moment, intimate moments weighted 2× (appear twice in the pool)."""
    rng = rng or random.Random()
    used = recent_keys(history)
    last = {k: i for i, k in enumerate(used)}
    # Intimate moments are added twice so they are roughly 2× more likely when recency is equal
    pool = []
    for m in MOMENTS:
        pool.append(m)
        if m.get('intimate'):
            pool.append(m)
    order = sorted(pool, key=lambda m: (last.get(m['key'], -1), rng.random()))
    return order[0]


def framing(m):
    return (m or {}).get('framing') or MID


def help_text():
    return '\n'.join(f"{m['aliases'][0] if m.get('aliases') else m['key']} - {m['name']}" for m in MOMENTS)
