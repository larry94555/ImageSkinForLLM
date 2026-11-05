import { render } from "preact";

import { App } from "./App";
import { watchForInactiveAccount } from "./inactive-account";
import { sendFetchesUnderSitePath } from "./site-path";
import "./styles.css";

sendFetchesUnderSitePath();
// After it, so its own calls go under the trial site's path too.
watchForInactiveAccount();

render(<App />, document.getElementById("root") as HTMLElement);
