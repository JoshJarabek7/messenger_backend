![Agave plant, close-up. Beautiful natural background][image1]

# ChatGenius: smarter workplace communication with AI

# Background and context

Chat apps, such as Slack, are a foundational element of the modern workplace. If you work remotely, they *are* the workplace \- and even if you work in-person, chat apps enable asynchronous collaboration and integration with other common tools.

But chat apps aren’t perfect \- written text lacks the nuance of the voice and facial expressions. Chatting can be less engaging, or even less accurate, with people missing key pieces of information.

ChatGenius tackles this by applying generative AI, not to replace humans but to augment them. It gives the user a professional digital twin, an AI avatar that can represent them but still have a personal touch.

### Submission Guidelines

At the end of each week you’ll be required to submit the following to the GauntletAI Platform:

1. A link to the code of the project in Github  
2. The Brainlift you used in learning to build the application (and anything you used to feed to a model to make building the application better).  
3. A 5 minute walkthrough of you showing the world what you’ve built (and where relevant, how you’ve built it). The more impressive this is the better.  
4. The link to you sharing this project on X, and interacting with any feedback.

# Baseline App (Week 1\)

Our first week is spent building the application itself using AI-first principles.

Some topics and techniques have not yet been covered in class, but you are not prevented from using them.

For a baseline reference app, consider Slack \- it is the dominant tool in this space, providing excellent UX and integration with a rich ecosystem.

For the purposes of developing ChatGenius, here are the core features you should target:

1. Authentication  
2. Real-time messaging  
3. Channel/DM organization  
4. File sharing & search  
5. User presence, & status  
6. Thread support  
7. Emoji reactions

IDEs such as Cursor and any other AI tools are all fair game, as well as building on related open source projects (though doublecheck that the license is compatible with potential commercial use).

# AI Objectives (Week 2\)

Once you’ve built the app itself, it’s time to add AI\! The high-level goal is an AI avatar that represents users in conversations and meetings. Baseline functionality should include:

* Given a prompt, can create and send communication on behalf of the user  
  * This communication should be informed by content on the Slack, i.e. context-aware  
  * It should mirror the personality of the user, i.e. “sound” like them  
* If another Slack user has a question for the user (or their avatar), the avatar can receive and respond to it automatically without user intervention

Advanced features to consider:

* Voice synthesis \- deliver messages via synthesized voice

* Video synthesis \- deliver messages via synthesized video / visual avatar

* Allow the user to customize the look and style of their avatar

  * This could be to match them (they upload voice/pictures/video)

  * And/or you could allow them to select from other custom options

* Gesture/expression generation \- enable more sophisticated expression by the avatar

These features are only guidelines \- your main goal is to build a great app. So, if you come up with other ideas, feel free to implement them\!

# AI Tools and Techniques

You’ll need to dive into prompt engineering, templates, and possibly the basics of RAG or fine-tuning.

* [Prompt engineering \- OpenAI API](https://platform.openai.com/docs/guides/prompt-engineering) \- LLM output is largely a function of their prompt, so getting a tight feedback loop to iterate on prompts is key  
* [Prompt Templates | 🦜️🔗 LangChain](https://python.langchain.com/docs/concepts/prompt_templates/) \- powerful prompts incorporate information from the real-world, such as relevant chat messages  
* [Build a Retrieval Augmented Generation (RAG) App: Part 1 | 🦜️🔗 LangChain](https://python.langchain.com/docs/tutorials/rag/) \- RAG is one of the main ways we enhance AI apps, giving them access to a large corpus of relevant content without going to the trouble of retraining them  
* [OpenAI Platform Fine Tuning](https://platform.openai.com/docs/guides/fine-tuning) \- if you want to change an LLM itself, and you collect some data (such as user chats),  you can fine-tune it so it behaves more like the data you give it

If you dig into the advanced visual/video avatar, we recommend checking out services like [D-ID](https://www.d-id.com/) and [HeyGen](https://www.heygen.com/). They are specifically designed to create avatars and video content based on humans, and offer advanced functionality that may inspire you to create extra features.

We also highly recommend using an AI observability platform, such as [Langfuse](https://langfuse.com/), to facilitate monitoring and debugging your application. It can also help gathering and labeling data for potential future use.

# Scope and deliverables

| Deliverable | Description |
| :---- | :---- |
| Chat app | Working chat web app that enables, at minimum, real-time messaging between users in channels \-  more features are welcome\! |
| AI augmentation \- baseline | Chat app users can create a virtual avatar for themselves that can send chats based on their own chat history. |
| AI augmentation \- stretch | Avatar is more sophisticated \- audio/video, humanized expression, better/more relevant context and content, etc. Come up with your own ideas too\! |

# Milestones

| Completion date | Project phase | Description |
| :---- | :---- | :---- |
| Jan 7, 2025 | Chat app MVP | You should have a working chat app with at least messaging and channel functionality by this point. |
| Jan 8, 2025 | Check in 1 |  |
| Jan 10, 2025 | App complete | On Friday you should have completed your app. |
| Jan 13, 2025 | AI Objectives start |  |
| Jan 15, 2025 | Check in 2 |  |
| Jan 17, 2025 | AI features complete | On Friday you should have completed the AI objectives |

# Resources

[Mattermost](https://github.com/mattermost/mattermost) \- an open-source Slack alternative  
[LangChain](https://www.langchain.com/) \- a framework for rapid development of AI-powered applications

# Suggested steps

- [ ] Plan initial approach, ensure AI development tools are set up

- [ ] Get MVP functionality working

- [ ] Iterate on MVP until it hits acceptable baseline of features

- [ ] Select AI augmentation(s)

- [ ] Implement AI augmentations, with focus on rapid runnable MVP to get feedback and tight iteration loop

You’re encouraged to share your progress as you go, both for camaraderie and competition. You can also ask questions in Slack any time.
