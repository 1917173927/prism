import { marked } from "marked";
import DOMPurify from "dompurify";

// DOM fragments avoid an unsanitized HTML assignment anywhere in application code.
window.PrismMarkdown = (target, source) => {
  const fragment = DOMPurify.sanitize(marked.parse(String(source), { gfm: true, breaks: true }), {
    RETURN_DOM_FRAGMENT: true,
    ALLOWED_TAGS: ["p", "br", "strong", "em", "del", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "pre", "code", "table", "thead", "tbody", "tr", "th", "td", "a", "hr"],
    ALLOWED_ATTR: ["href", "title", "start"],
  });
  for (const link of fragment.querySelectorAll("a")) {
    if (!/^(https?:\/\/|#)/i.test(link.getAttribute("href") || "")) link.removeAttribute("href");
    link.setAttribute("rel", "noopener noreferrer");
  }
  target.replaceChildren(fragment);
};
