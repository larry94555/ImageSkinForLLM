"""Makes sample.pdf, the sample PDF of about 20 pages that `imageskin time-pdf` times (roadmap
R96a): text, a table and formulas on prime numbers and the zeta function, written for this
project. Run it from the repository's root with reportlab installed (`pip install -e .[dev]`):

    python experiments/speed/make_sample_pdf.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table

OUT = Path(__file__).with_name("sample.pdf")

TITLE = "Prime Numbers and the Zeta Function: A Short Guide"

# Each section starts a page: (heading, paragraphs). A paragraph starting with "=" is a formula.
SECTIONS = [
    (
        "1. What a prime number is",
        [
            "A prime number is a whole number greater than one whose only divisors are one and "
            "itself. Two, three, five, seven and eleven are prime. Four is not, because it is "
            "two times two, and nine is not, because it is three times three. A whole number "
            "greater than one that is not prime is called composite.",
            "The number one is not counted as a prime. This is a choice rather than a "
            "discovery, but it is a useful one: if one were prime, a number could be written "
            "as a product of primes in many ways, by adding as many ones as we liked, and the "
            "most important fact about primes would need a long list of exceptions.",
            "Two is the only even prime. Every other even number can be divided by two, so it "
            "has a divisor besides one and itself. This makes two an odd prime out in many "
            "statements, and mathematicians often speak of the odd primes when they want to "
            "leave it aside.",
            "Primes have been studied for at least two and a half thousand years. Greek "
            "mathematicians knew how to find them, knew that there are infinitely many of "
            "them, and knew that every whole number is built from them in exactly one way. "
            "Much of what is still unknown about primes concerns how they are spread out "
            "among the other numbers.",
        ],
    ),
    (
        "2. Building every number from primes",
        [
            "The fundamental theorem of arithmetic says that every whole number greater than "
            "one can be written as a product of primes, and that this product is unique apart "
            "from the order of its factors. For example, 360 is two times two times two times "
            "three times three times five, and there is no other way to write it as a product "
            "of primes.",
            "= 360 = 2^3 x 3^2 x 5",
            "The existence part is easy: if a number is not prime, split it into two smaller "
            "factors, and keep splitting until every piece is prime. The uniqueness part is "
            "harder. It rests on a fact proved by Euclid: if a prime divides a product of two "
            "numbers, it must divide at least one of them.",
            "Because of this theorem, primes are often called the atoms of arithmetic. "
            "Questions about whole numbers can often be turned into questions about their "
            "prime factors. The greatest common divisor of two numbers, for instance, is found "
            "by taking each prime to the smaller of the two powers in which it appears.",
            "The theorem also explains why factoring large numbers matters in practice. "
            "Multiplying two large primes is quick, but recovering them from their product is "
            "believed to be very slow when the primes have hundreds of digits. Much of the "
            "encryption used on the internet depends on that difference.",
        ],
    ),
    (
        "3. There are infinitely many primes",
        [
            "Euclid gave a proof, more than two thousand years ago, that the primes never run "
            "out. Suppose there were only finitely many primes. Multiply all of them together "
            "and add one. The new number leaves a remainder of one when divided by any prime "
            "on the list, so none of them divides it. But every number greater than one has a "
            "prime factor, so there must be a prime missing from the list.",
            "The proof does not say that the new number is itself prime. Two times three times "
            "five times seven times eleven times thirteen, plus one, is 30031, which is 59 "
            "times 509. What the proof shows is that some prime is missing from any finite "
            "list, and so no finite list can contain them all.",
            "Many other proofs have been found since. One of the most important, due to "
            "Leonhard Euler in the eighteenth century, shows something stronger: the sum of "
            "the reciprocals of the primes grows without limit. This means the primes are not "
            "only infinite in number but fairly common, far more common than the perfect "
            "squares, whose reciprocals add up to a finite total.",
            "= 1/2 + 1/3 + 1/5 + 1/7 + 1/11 + ... grows without limit",
            "Euler's proof is the first step on the road that leads to the zeta function, "
            "which is described later in this guide.",
        ],
    ),
    (
        "4. Finding primes: the sieve of Eratosthenes",
        [
            "The oldest practical way to list primes is the sieve of Eratosthenes, named after "
            "a Greek scholar who lived in Alexandria around 240 BC. To find every prime up to "
            "a limit, write down all the numbers from two to the limit. Circle two, and cross "
            "out every larger multiple of two. Then circle the next number not crossed out, "
            "which is three, and cross out its multiples. Keep going.",
            "The numbers circled are exactly the primes. It is enough to sieve with primes up "
            "to the square root of the limit: any composite number below the limit has a "
            "prime factor no larger than its square root, so it has already been crossed out "
            "by the time that point is reached.",
            "The sieve is fast. Listing the primes below one million takes a modern computer "
            "a few milliseconds. Its weakness is memory, since every number up to the limit "
            "must be kept, so for very large ranges the sieve is run on one segment at a time.",
            "To test a single large number, sieving is far too slow. Modern tests, such as "
            "the Miller-Rabin test, check a property that every prime has and that almost "
            "every composite number lacks. They can decide whether a number with hundreds of "
            "digits is prime in a fraction of a second.",
        ],
    ),
    (
        "5. How many primes there are",
        [
            "Counting primes shows a steady thinning. One in four of the numbers below one "
            "hundred is prime, but only about one in thirteen of those below one million. The "
            "function that counts the primes up to a number x is written pi(x), which has "
            "nothing to do with the circle constant.",
            "The table below gives pi(x) for powers of ten, together with x divided by the "
            "natural logarithm of x, which is the estimate given by the prime number theorem.",
            "TABLE",
            "The estimate is always a little low, but the ratio between the true count and "
            "the estimate gets closer to one as x grows. Carl Friedrich Gauss noticed this "
            "pattern as a teenager, around 1792, by studying tables of primes. It was proved "
            "a century later, in 1896, independently by Jacques Hadamard and Charles de la "
            "Vallee Poussin, using the zeta function.",
        ],
    ),
    (
        "6. The prime number theorem",
        [
            "The prime number theorem says that the number of primes up to x is roughly x "
            "divided by the natural logarithm of x, in the sense that the ratio of the two "
            "tends to one as x grows without limit.",
            "= pi(x) ~ x / ln(x)",
            "Put another way, near a large number x, about one number in every ln(x) is prime. "
            "Near one million, ln(x) is about 13.8, so roughly one number in fourteen is prime. "
            "Near one trillion, ln(x) is about 27.6, and the primes are half as dense again.",
            "A better estimate is the logarithmic integral, Li(x), which adds up one over the "
            "logarithm of every number up to x. Gauss suggested it, and it is remarkably "
            "accurate: for x equal to ten to the power of ten, Li(x) is off from the true "
            "count by only about three thousand, out of four hundred and fifty five million.",
            "How large the error in Li(x) can be is one of the central questions of number "
            "theory. The Riemann hypothesis, if it is true, says that the error is never much "
            "larger than the square root of x. That is the best that could be hoped for, and "
            "it is what makes the hypothesis so important.",
        ],
    ),
    (
        "7. Euler and the zeta function",
        [
            "In 1737 Leonhard Euler studied the infinite sum of one over n to the power s, "
            "for numbers s greater than one. This sum is now called the zeta function, "
            "written zeta(s).",
            "= zeta(s) = 1 + 1/2^s + 1/3^s + 1/4^s + ...",
            "Euler found that this sum over all whole numbers equals a product over all the "
            "primes. Each prime p contributes a factor of one divided by the quantity one "
            "minus one over p to the power s. This is called the Euler product.",
            "= zeta(s) = product over primes p of 1 / (1 - 1/p^s)",
            "The Euler product is the fundamental theorem of arithmetic written as an "
            "equation: expanding each factor as a geometric series and multiplying them out "
            "gives every product of prime powers exactly once, which means every whole number "
            "exactly once. It links the primes, which are irregular, to a sum over all the "
            "whole numbers, which is perfectly regular.",
            "Euler used it to prove again that there are infinitely many primes. As s comes "
            "down to one, the sum becomes the harmonic series, which grows without limit. If "
            "there were only finitely many primes, the product would stay finite, so there "
            "must be infinitely many.",
        ],
    ),
    (
        "8. The Basel problem",
        [
            "Before he found the Euler product, Euler made his name by solving the Basel "
            "problem, which had defeated the best mathematicians for ninety years. The "
            "problem asked for the exact value of the sum of the reciprocals of the squares.",
            "= 1 + 1/4 + 1/9 + 1/16 + ... = pi^2 / 6",
            "Euler announced in 1734 that the sum is pi squared over six, about 1.6449. In "
            "the language of the zeta function, zeta(2) equals pi squared over six. The "
            "appearance of pi, a number from geometry, in a sum about whole numbers was a "
            "great surprise.",
            "Euler went on to find zeta(s) for every even number s. Each is a rational number "
            "times pi to the power s. For example, zeta(4) is pi to the fourth over ninety. "
            "The odd values are much more mysterious. In 1978 Roger Apery proved that zeta(3) "
            "is irrational, but nobody knows a simple formula for it, and very little is "
            "known about zeta(5), zeta(7) and the rest.",
            "Combining Euler's two discoveries gives a pleasant fact: the chance that two "
            "whole numbers chosen at random have no common factor is six over pi squared, "
            "about 61 percent.",
        ],
    ),
    (
        "9. Riemann's paper of 1859",
        [
            "Bernhard Riemann, a German mathematician, wrote only one paper on number theory. "
            "Published in 1859 and only eight pages long, it changed the subject. Riemann "
            "treated zeta(s) as a function of a complex number s, a number with a real part "
            "and an imaginary part, rather than only a real one.",
            "The sum that defines zeta(s) only makes sense when the real part of s is greater "
            "than one. Riemann showed how to extend the function to every complex number "
            "except s equal to one, where it has a pole. He also found a symmetry, the "
            "functional equation, that relates the value at s to the value at one minus s.",
            "Riemann then gave an exact formula for counting primes. It expresses the number "
            "of primes up to x as a main term, close to Li(x), plus a correction for every "
            "zero of the zeta function. The zeros act like the notes of a chord: each adds a "
            "wave to the count, and together they reproduce the exact step where each prime "
            "appears.",
            "The zeta function has trivial zeros at the negative even numbers, minus two, "
            "minus four and so on. All of its other zeros, the nontrivial ones, lie in the "
            "critical strip, where the real part of s is between zero and one. Where exactly "
            "they lie decides how well the primes follow the prime number theorem.",
        ],
    ),
    (
        "10. The Riemann hypothesis",
        [
            "Riemann suggested, almost in passing, that all the nontrivial zeros of the zeta "
            "function have real part exactly one half. They would then lie on a single line "
            "in the middle of the critical strip, now called the critical line. This "
            "suggestion is the Riemann hypothesis.",
            "= every nontrivial zero of zeta(s) has real part 1/2",
            "The hypothesis has been checked for the first ten trillion zeros, and every one "
            "of them lies on the critical line. It has not been proved. In 1900 David Hilbert "
            "put it on his list of the most important open problems, and in 2000 the Clay "
            "Mathematics Institute made it one of its seven Millennium Prize Problems, with a "
            "prize of one million dollars for a proof.",
            "If it is true, the primes are as regular as they could possibly be: the error in "
            "the prime number theorem is about the square root of x, no larger. Hundreds of "
            "theorems have been proved on the assumption that it is true, so a proof would "
            "settle all of them at once. A disproof would be just as dramatic.",
            "Some partial results are known. Godfrey Hardy proved in 1914 that infinitely "
            "many zeros lie on the critical line, and later work showed that at least two "
            "fifths of them do. None of these comes close to all of them.",
        ],
    ),
    (
        "11. Primes and the zeta function in physics",
        [
            "In 1972 the mathematician Hugh Montgomery was studying the spacing between zeros "
            "of the zeta function. Over tea at Princeton, the physicist Freeman Dyson "
            "recognized his formula: it was the same as the spacing between energy levels of "
            "heavy atomic nuclei, as described by random matrix theory.",
            "Since then, computations by Andrew Odlyzko of millions of zeros high on the "
            "critical line have matched the predictions of random matrix theory with great "
            "accuracy. Many researchers now suspect that the zeros are the energy levels of "
            "some quantum system that has not yet been found. If it were found, the Riemann "
            "hypothesis might follow from the laws of quantum mechanics.",
            "The zeta function appears elsewhere in physics as well. The value zeta(3) turns "
            "up in the energy of black body radiation and in quantum electrodynamics. The "
            "Casimir effect, a tiny force between two metal plates in a vacuum, is often "
            "explained with a method called zeta function regularization, which gives a "
            "finite meaning to sums that would otherwise grow without limit.",
            "These links are still not fully understood, which is part of what makes the "
            "subject so active.",
        ],
    ),
    (
        "12. Open questions about primes",
        [
            "Besides the Riemann hypothesis, many simple questions about primes are still "
            "open. The twin prime conjecture says that there are infinitely many pairs of "
            "primes that differ by two, such as 11 and 13, or 41 and 43. In 2013 Yitang Zhang "
            "proved that there are infinitely many pairs of primes that differ by less than "
            "seventy million, and later work brought that bound down to 246.",
            "Goldbach's conjecture, from a letter Christian Goldbach wrote to Euler in 1742, "
            "says that every even number greater than two is the sum of two primes. It has "
            "been checked by computer up to four quintillion, and in 2013 Harald Helfgott "
            "proved the weaker version for odd numbers: every odd number greater than five is "
            "the sum of three primes.",
            "Other questions ask whether there are infinitely many primes of the form n "
            "squared plus one, or how long a run of composite numbers can be found below a "
            "given size. Each sounds simple, and each has resisted the best efforts of "
            "mathematicians for a century or more.",
            "Prime numbers are among the oldest objects of study in mathematics, and they "
            "still hold some of its deepest mysteries.",
        ],
    ),
    (
        "13. Primes in arithmetic progressions",
        [
            "Apart from two and five, every prime ends in the digit one, three, seven or nine. "
            "A natural question is whether the primes are shared out evenly among these four "
            "endings. They are: in the long run, a quarter of the primes end in each digit.",
            "This is a special case of a theorem proved by Peter Gustav Lejeune Dirichlet in "
            "1837. Take any two whole numbers a and q with no common factor. Then the "
            "progression a, a plus q, a plus two q, and so on contains infinitely many primes. "
            "For example, there are infinitely many primes that leave a remainder of one when "
            "divided by four, such as 5, 13, 17 and 29, and infinitely many that leave a "
            "remainder of three, such as 3, 7, 11 and 19.",
            "Dirichlet's proof was a landmark because it used analysis, the mathematics of "
            "limits and continuous functions, to answer a question about whole numbers. He "
            "built functions much like the zeta function, now called Dirichlet L-functions, "
            "with one for each way of sorting numbers by their remainders.",
            "Although the primes are shared out evenly in the long run, there are curious "
            "biases along the way. Primes that leave a remainder of three when divided by four "
            "are ahead of those that leave a remainder of one for most of the way. This is "
            "known as Chebyshev's bias, after Pafnuty Chebyshev, who noticed it in 1853.",
            "In 2016 Robert Lemke Oliver and Kannan Soundararajan found a related surprise: "
            "consecutive primes seem to avoid repeating their last digit. A prime ending in "
            "one is followed by another prime ending in one less often than chance would "
            "suggest.",
        ],
    ),
    (
        "14. Mersenne primes and perfect numbers",
        [
            "A Mersenne number is one less than a power of two, such as 3, 7, 31 and 127. They "
            "are named after Marin Mersenne, a French monk who studied them in the seventeenth "
            "century. A Mersenne number can only be prime if its exponent is prime, but a "
            "prime exponent is not enough: two to the eleventh minus one is 2047, which is 23 "
            "times 89.",
            "= M(p) = 2^p - 1",
            "Mersenne primes are linked to perfect numbers, numbers equal to the sum of their "
            "proper divisors. Six is perfect, because one plus two plus three is six, and so "
            "is 28. Euclid showed that whenever two to the p minus one is prime, multiplying "
            "it by two to the p minus one gives a perfect number. Euler later proved that "
            "every even perfect number arises this way. Whether an odd perfect number exists "
            "is still unknown.",
            "The largest known primes are almost all Mersenne primes, because there is a fast "
            "test for them, the Lucas-Lehmer test. The Great Internet Mersenne Prime Search, "
            "a project in which volunteers lend their computers, has found every record prime "
            "since 1996. The largest known prime, found in 2024, has more than forty one "
            "million digits.",
            "Only about fifty Mersenne primes are known. It is believed that there are "
            "infinitely many of them, but this has not been proved.",
        ],
    ),
    (
        "15. Primes and cryptography",
        [
            "Prime numbers protect much of the information sent over the internet. The RSA "
            "system, published in 1977 by Ron Rivest, Adi Shamir and Leonard Adleman, uses two "
            "large secret primes. Their product is made public and is used to lock messages; "
            "only someone who knows the two primes can unlock them.",
            "The security of RSA rests on the difficulty of factoring. Multiplying two primes "
            "of three hundred digits each takes a computer a tiny fraction of a second, but no "
            "known method running on ordinary computers can recover the primes from their "
            "product in any reasonable time.",
            "Making RSA keys needs a supply of large primes. The prime number theorem says "
            "they are plentiful: about one in every seven hundred numbers with three hundred "
            "digits is prime, so a computer picks random numbers of the right size and tests "
            "them until it finds one. Fast primality tests make this quick.",
            "Other systems use primes in different ways. Elliptic curve cryptography works "
            "with points on curves whose coordinates are taken modulo a large prime, and gives "
            "the same security as RSA with much shorter keys.",
            "A large enough quantum computer could factor large numbers quickly, using an "
            "algorithm found by Peter Shor in 1994. For this reason, new systems based on "
            "other hard problems are now being adopted, in what is called post-quantum "
            "cryptography.",
        ],
    ),
    (
        "16. Gaps between primes",
        [
            "The gap between two consecutive primes is the difference between them. Apart "
            "from the gap of one between two and three, every gap is even. On average, the gap "
            "near a number x is about ln(x), as the prime number theorem suggests, but single "
            "gaps can be much smaller or much larger.",
            "Long gaps are easy to build. The numbers from one hundred factorial plus two to "
            "one hundred factorial plus one hundred are all composite, because the first is "
            "divisible by two, the next by three, and so on. So there are gaps as long as we "
            "like, although they appear only among very large numbers.",
            "Short gaps are much harder. The smallest possible gap between odd primes is two, "
            "and the twin prime conjecture says that this gap occurs infinitely often. "
            "Zhang's result of 2013, improved by James Maynard, Terence Tao and the Polymath "
            "project, shows that some gap of at most 246 occurs infinitely often.",
            "There are also limits on how long gaps can be. Bertrand's postulate, proved by "
            "Chebyshev in 1852, says that there is always a prime between any number n and "
            "two n. It is believed that there is always a prime between any two consecutive "
            "squares, but this is Legendre's conjecture and is still open.",
        ],
    ),
    (
        "17. Computing the zeros of the zeta function",
        [
            "Riemann himself computed the first few zeros of the zeta function by hand, as "
            "notes found in his papers decades later revealed. The first zero lies on the "
            "critical line at a height of about 14.13.",
            "= first zeros: 1/2 + 14.13i, 1/2 + 21.02i, 1/2 + 25.01i",
            "In 1903 Jorgen Gram checked the first fifteen zeros. Alan Turing, better known "
            "for his work on computing and code breaking, designed a method in the 1950s for "
            "checking that no zeros are missed, and used one of the first electronic "
            "computers to check more than a thousand of them.",
            "Today, a method by Andrew Odlyzko and Arnold Schonhage makes it possible to "
            "compute many zeros at once. The first ten trillion zeros have all been found on "
            "the critical line, and zeros near the ten to the twenty second zero have been "
            "computed to study their spacing.",
            "No amount of computing can prove the Riemann hypothesis, since there are "
            "infinitely many zeros. But the computations have found no exception, and they "
            "have revealed the statistical patterns that link the zeros to random matrices "
            "and physics.",
        ],
    ),
    (
        "18. A short timeline",
        [
            "Around 300 BC, Euclid proves that there are infinitely many primes and lays the "
            "groundwork for the fundamental theorem of arithmetic. Around 240 BC, Eratosthenes "
            "describes his sieve.",
            "In 1734 Euler solves the Basel problem, and in 1737 he finds the Euler product. "
            "In 1742 Goldbach writes to Euler with his conjecture. Around 1792 Gauss guesses "
            "the prime number theorem from tables of primes.",
            "In 1837 Dirichlet proves his theorem on primes in arithmetic progressions. In "
            "1859 Riemann publishes his paper on the zeta function and states his hypothesis. "
            "In 1896 Hadamard and de la Vallee Poussin prove the prime number theorem.",
            "In 1914 Hardy proves that infinitely many zeros lie on the critical line. In 1972 "
            "Montgomery and Dyson find the link between the zeros and random matrices. In 1977 "
            "RSA is published. In 2013 Zhang proves that bounded gaps between primes occur "
            "infinitely often, and Helfgott proves the weak Goldbach conjecture.",
            "The Riemann hypothesis, the twin prime conjecture and Goldbach's conjecture all "
            "remain open.",
        ],
    ),
]

# The number of primes up to x, and x / ln(x), for the powers of ten.
TABLE = [
    ["x", "Primes up to x", "x / ln(x)", "Ratio"],
    ["10", "4", "4.3", "0.921"],
    ["100", "25", "21.7", "1.151"],
    ["1,000", "168", "144.8", "1.161"],
    ["10,000", "1,229", "1,085.7", "1.132"],
    ["100,000", "9,592", "8,685.9", "1.104"],
    ["1,000,000", "78,498", "72,382.4", "1.084"],
    ["10,000,000", "664,579", "620,420.7", "1.071"],
]


def build(out: Path = OUT) -> Path:
    styles = getSampleStyleSheet()
    body = styles["BodyText"].clone("body", fontSize=13, leading=21, spaceAfter=10)
    formula = body.clone("formula", fontName="Courier", leftIndent=36)
    story = [Paragraph(TITLE, styles["Title"]), Spacer(1, 0.3 * inch)]
    story.append(
        Paragraph(
            "This guide introduces prime numbers, how they are found and counted, and the "
            "zeta function that connects them to the rest of mathematics and to physics.",
            body,
        )
    )
    for heading, paragraphs in SECTIONS:
        story += [PageBreak(), Paragraph(heading, styles["Heading1"])]
        for text in paragraphs:
            if text == "TABLE":
                story += [Table(TABLE, hAlign="LEFT"), Spacer(1, 0.2 * inch)]
            elif text.startswith("= "):
                story.append(Paragraph(text[2:], formula))
            else:
                story.append(Paragraph(text, body))
    doc = SimpleDocTemplate(
        str(out), pagesize=letter, leftMargin=1.25 * inch, rightMargin=1.25 * inch
    )
    doc.build(story)
    return out


if __name__ == "__main__":
    print(f"Wrote {build()}")
