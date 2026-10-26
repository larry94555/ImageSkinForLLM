"""R129's three long replies, of about 150, 220 and 300 words, written the way Gemma 3 4B answers
in the app: paragraphs of plain sentences, some long with commas, and a short list. With
fake_llm.py they are what the LLM "writes", so every run speaks the same words."""

PROMPTS = (
    "Tell me about the history of the bicycle.",
    "How do bees make honey?",
    "What should I know before I start running?",
)

REPLIES = {
    PROMPTS[0]: (
        "The bicycle has a surprisingly long and interesting history. The first one, called the "
        "running machine, was built by Karl Drais in Germany in 1817. It had two wheels and a "
        "wooden frame, but no pedals, so riders pushed themselves along with their feet.\n\n"
        "In the 1860s, French makers added pedals to the front wheel, and the result was nicknamed "
        "the boneshaker, because its iron tyres made every ride rough and noisy. Soon after came "
        "the penny farthing, with a huge front wheel that let riders go faster, although falling "
        "off it could be quite dangerous.\n\n"
        "The real change came in 1885, when John Kemp Starley built the safety bicycle. It had two "
        "wheels of the same size and a chain that drove the back wheel, which is still the design "
        "we use today. With air-filled tyres added a few years later, cycling became comfortable, "
        "safe and popular all over the world."
    ),
    PROMPTS[1]: (
        "Bees make honey through a careful process that turns flower nectar into a thick, sweet "
        "food they can store for the winter.\n\n"
        "It starts with the forager bees. They fly from flower to flower, sometimes visiting "
        "hundreds in a single trip, and suck up the nectar with their long tongues. The nectar is "
        "kept in a special honey stomach, separate from the stomach they use for their own food. "
        "While it is there, enzymes begin to break down the sugars in the nectar.\n\n"
        "When a forager returns to the hive, she passes the nectar to a house bee, mouth to mouth. "
        "The house bee chews it for a while, adding more enzymes, and then passes it on again. "
        "This is repeated several times, until the nectar has changed into an early form of "
        "honey.\n\n"
        "Next, the bees spread the liquid into the wax cells of the honeycomb. At this point it is "
        "still very watery, so the bees fan it with their wings to help the water evaporate. When "
        "the honey is thick enough, with less than about twenty percent water, they seal each "
        "cell with a thin cap of wax.\n\n"
        "A single bee makes only about a twelfth of a teaspoon of honey in her whole life, so a "
        "jar of honey is the work of thousands of bees."
    ),
    PROMPTS[2]: (
        "Starting to run is a great choice for your health, and a little preparation will make it "
        "much more enjoyable. Here are the most important things to know before you begin.\n\n"
        "First, get a good pair of running shoes. Your shoes are the only real equipment you need, "
        "so it is worth visiting a running store, where the staff can watch you run and suggest a "
        "pair that suits your feet and your stride.\n\n"
        "Second, start slowly. Many beginners try to do too much in the first few weeks, and that "
        "is how injuries happen. A good plan is to mix running and walking, for example one minute "
        "of running followed by two minutes of walking, repeated for about twenty minutes. Over "
        "several weeks, you can run for longer and walk for less.\n\n"
        "Third, warm up and cool down. Walk briskly for five minutes before you run, and walk "
        "again for a few minutes afterwards, so your heart rate comes down gently.\n\n"
        "Here are a few more tips:\n\n"
        "- Run at a pace where you can still hold a conversation.\n"
        "- Drink water before and after your run, especially on hot days.\n"
        "- Rest at least one day between runs at first, so your body can recover.\n"
        "- Listen to your body, and stop if something hurts.\n\n"
        "Finally, be patient with yourself. Progress in running comes gradually, and everyone "
        "starts somewhere. If you keep going for a couple of months, you will probably be "
        "surprised by how much easier it feels and how much further you can go. Good luck, and "
        "enjoy your first runs!"
    ),
}
