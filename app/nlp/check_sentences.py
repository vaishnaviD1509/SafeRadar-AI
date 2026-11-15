"""A small set of hand-written sentences for a sanity check.

They were written by hand in different words from the generator's templates, to see
whether the model copes with wording it has not memorised. The labels are the writer's
own reading and a few are genuinely arguable. With only 32 sentences the score is a rough
indication, NOT a reliable accuracy figure. The model never trains on these.
"""

CHECK_SENTENCES = [
    # Harassment
    ("Two guys on a scooter kept shouting rude things at me when I crossed the road.", "Harassment"),
    ("A man brushed against me on purpose inside the crowded bus.", "Harassment"),
    ("A shopkeeper made inappropriate jokes about my clothes and would not stop even after I asked him to.", "Harassment"),
    ("Some boys were passing vulgar comments as I walked to my coaching class.", "Harassment"),
    ("He grabbed my hand in the queue and laughed when I pulled away.", "Harassment"),
    ("A man sitting next to me in the auto kept staring and making kissing sounds.", "Harassment"),
    ("A group of youngsters whistled and teased me every time I passed the tea stall.", "Harassment"),
    ("Men near the wine shop passed ugly remarks about me as I walked by.", "Harassment"),
    # Stalking
    ("The same man has been trailing me on my way to office all this week.", "Stalking"),
    ("A car kept driving behind me slowly for two streets and followed me until I reached my gate.", "Stalking"),
    ("I noticed someone tailing me from the market, so I changed my route twice and he still came after me.", "Stalking"),
    ("A guy from my college waits outside my hostel every evening and walks behind me wherever I go.", "Stalking"),
    ("He was clicking my pictures secretly and kept coming after me to the next stop.", "Stalking"),
    ("A man on a motorcycle kept circling around me as I walked to the pharmacy.", "Stalking"),
    ("Somebody has been watching my house and tracking my movements for days.", "Stalking"),
    ("A stranger got off the bus at my stop and followed me all the way to my lane.", "Stalking"),
    # Threats
    ("My neighbour warned me he would hurt me if I told anyone.", "Threats"),
    ("A drunk man raised his fist and said he would beat me up if I did not move.", "Threats"),
    ("Some men told me I would regret it and that they know where I live.", "Threats"),
    ("He showed a knife and told me to keep quiet or face the consequences.", "Threats"),
    ("An auto driver shouted that he would make me pay after I refused his fare.", "Threats"),
    ("Someone left a note saying I would be harmed if I filed a complaint.", "Threats"),
    ("A man yelled abuse and promised to teach me a lesson near the bus stop.", "Threats"),
    ("They said they would break my phone and hit me if I reported them.", "Threats"),
    # Unsafe surroundings
    ("There is no lighting at all on this stretch and it is pitch black after seven.", "Unsafe surroundings"),
    ("The underpass is deserted and smells of liquor, nobody is ever around there.", "Unsafe surroundings"),
    ("The road near the lake has no streetlamps and no shops open, completely isolated at night.", "Unsafe surroundings"),
    ("Construction material is blocking the footpath and the lane is dark with dogs roaming around.", "Unsafe surroundings"),
    ("The bus shelter has a broken bulb and a group of men sit there drinking every night.", "Unsafe surroundings"),
    ("Empty ground behind the station with no guards, scary to cross alone.", "Unsafe surroundings"),
    ("The alley is narrow, unlit and full of garbage, I avoid it after sunset.", "Unsafe surroundings"),
    ("No police patrol and no people on this lonely road, the lights have been out for weeks.", "Unsafe surroundings"),
]