# Donor accent recordings

Short recordings of people with an accent, for the accent test's `--donor` option
(`accent_test.py`, R26a). They are 24 kHz mono 16-bit WAVs, the voice-sample format, so they are
passed in directly. The test learns the donor's voice from the first 10 seconds of speech.

| File | Speaker | Stands in for |
|---|---|---|
| `american-male.wav` | a man with a mainstream US accent (EdAcc speaker EDACC-C06-B) | American, for a man |
| `american-female.wav` | a woman with a mainstream US accent (EDACC-C14-A) | American, for a woman |
| `british-male.wav` | a man with a southern British accent (EDACC-C06-A) | British, for a man |
| `british-female.wav` | a woman with a southern British accent (EDACC-C11-B) | British, for a woman |
| `slavic-bulgarian-male.wav` | a man whose first language is Bulgarian (EDACC-C22-B) | Russian-English, for a man |
| `slavic-polish-female.wav` | a woman whose first language is Polish (EDACC-C07-B) | Russian-English, for a woman |

American and British also come from Kokoro's own voices, which are faster and studio-clean; the
donors are there to compare with a real person's way of speaking.

All come from the validation set of [EdAcc, the Edinburgh International Accents of English
Corpus](https://groups.inf.ed.ac.uk/edacc/) (Sanabria et al., 2023), published on Hugging Face as
`edinburghcstr/edacc` under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Changes: the speaker's longest conversation turns were joined, converted to 24 kHz mono and cut
to the first 20 seconds. These files are shared under the same license.

To use your own recording of someone with an accent (with their permission), make it a voice
sample first: `imageskin voice-sample donor.m4a -o donor.wav`.
