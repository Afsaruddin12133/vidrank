// www → apex 301: zone-level redirect rules need dashboard access; app middleware works everywhere.
// ponytail: single host check, no config needed. Remove if a CF Redirect Rule takes over.
export const onRequest = async (context, next) => {
  const url = new URL(context.request.url);
  if (url.hostname === "www.vidrank.tech") {
    return Response.redirect(`https://vidrank.tech${url.pathname}${url.search}`, 301);
  }
  return next();
};
