export function HomePage({ consented }: { consented: boolean }) {
  return (
    <>
      <h1>Welcome</h1>
      <p>
        Set up a talking video of a person from a few photos and voice recordings. The person then
        speaks the chatbot&apos;s replies.
      </p>
      <a className="button" href={consented ? "#/setup" : "#/consent"}>
        Start setup
      </a>
    </>
  );
}
