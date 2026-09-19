# HarneSkills

**An entity-component world, a loop that runs rules over it, and a prompt onto both.**

HarneSkills is a set of *doors* onto a `loopingrules` world:

- an **entity** is an identity with no data (`#7`);
- a **component** is data with no identity (`Size(bytes=4300)`);
- a **rule** is a Python function that asks for the entities carrying some components and walks them;
- the **loop** calls every rule, in order, until a whole pass changes nothing, at which point the world *settles* and has something to say.

This package supplies a terminal prompt, a WebSocket server and client, a config file for standing domains, and worked example domains. The engine itself lives in the sibling `loopingrules` project.

| If you want to... | Start here |
|---|---|
| Install it and talk to the file-system example | [Installation](user-guide/installation.md), [Quick start](user-guide/quickstart.md) |
| Know every flag and prompt command | [Command line](user-guide/cli.md), [At the prompt](user-guide/prompt.md) |
| Run it as a service several people can use | [Serving over WebSocket](user-guide/serving.md) |
| Understand how a turn works | [Architecture](developer-guide/architecture.md) |
| Write your own domain | [Writing a domain](developer-guide/writing-a-domain.md) |
