// SPDX-License-Identifier: Apache-2.0
import HelpMarkdown from "./HelpMarkdown";
import type { AssistantMessage } from "./assistantConversation";

// The help renderer escapes HTML and never fetches arbitrary Markdown images.
export default function AssistantMessageContent({ message }: { message: AssistantMessage }) {
  return <div className="assistant-chat__rich">
    <HelpMarkdown text={message.content || (message.attachments?.length ? "" : "Requested SPIKE action.")} source="" navigate={() => {}} hasTopic={() => false} />
    {message.attachments?.map(item => <figure className="assistant-chat__attachment" key={item.id}>
      {/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+=*$/.test(item.dataUrl) && <img src={item.dataUrl} alt={item.name} loading="lazy" />}
      <figcaption><a href={/^data:(image\/(png|jpeg|webp)|text\/plain);base64,[A-Za-z0-9+/]+=*$/.test(item.dataUrl) ? item.dataUrl : undefined} download={item.name}>{item.name}</a></figcaption>
    </figure>)}
  </div>;
}
