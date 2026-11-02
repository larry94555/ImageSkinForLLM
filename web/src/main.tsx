import { render } from "preact";

import { App } from "./App";
import { sendFetchesUnderSitePath } from "./site-path";
import "./styles.css";

sendFetchesUnderSitePath();

render(<App />, document.getElementById("root") as HTMLElement);
