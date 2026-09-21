/** A citation asks the source list to reveal and highlight one article. */
export const SHOW_ARTICLE_EVENT = "lens:show-article";

export function showArticle(articleId: string) {
  window.dispatchEvent(new CustomEvent<string>(SHOW_ARTICLE_EVENT, { detail: articleId }));
}
