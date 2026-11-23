# Human audit sheet

20 apps, 2 drawn at random from each of the 10 categories (seed 20261124). For each app, open the links and check the
agent's five answers against what the live docs say today.

**How to answer:** reply with only the items that are wrong, by their number, with what you found. For example:
`3.2 miss: API keys need the Team plan, so paid_plan` or `7.3 miss: no official MCP, only a community one`.
Anything you do not list is recorded as a hit, so please only skip an item you actually checked. If you could
not check an item, say `5.4 not checked` and it is left out of the score.

Values: access_level is one of self_serve_free, self_serve_trial, paid_plan, admin_approval, partner_or_sales, unknown.
mcp_status is official, community or none_found. verdict is buildable_now, buildable_with_caveats, blocked or unknown.

## 1. Salesforce (CRM and Sales)

API docs: <https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/intro_rest.htm>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 1.1 | primary_auth | oauth2 (also offers: other) | "For an external client app or connected app to request access, it must be integrated with your org’s REST API using the OAuth 2.0 protocol." — <https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/intro_oauth_and_connected_apps.htm><br>"When a client app invokes the login() call, it passes in a username and password as credentials." — <https://developer.salesforce.com/docs/atlas.en-us.api.meta/api/sforce_api_calls_login.htm> |
| 1.2 | access_level | self_serve_free | "Developer Edition provides a free and easy solution so that you can use Salesforce for testing and development. To sign up for a Developer Edition account, go to developer.salesforce.com/signup ." — <https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/quickstart_dev_org.htm><br>"This feature is enabled by default for Performance, Unlimited, Enterprise, and Developer Editions." — <https://developer.salesforce.com/docs/atlas.en-us.api.meta/api/sforce_api_quickstart_intro.htm> |
| 1.3 | mcp_status | official, unknown | "The Salesforce DX MCP Server is a specialized Model Context Protocol (MCP) implementation designed to facilitate seamless interaction between large language models (LLMs) and Salesforce orgs." — <https://github.com/salesforcecli/mcp><br>"The Salesforce DX local MCP server ( @salesforce/mcp ) reaches end of life on November 2nd, 2026." — <https://github.com/salesforcecli/mcp> |
| 1.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/salesforce |
| 1.5 | verdict | buildable_now | follows from access and API coverage: Free Developer Edition access and documented read/write APIs support building and testing a toolkit. Access to customer data requires an org and user with API access enabled. |

## 2. Pipedrive (CRM and Sales)

API docs: <https://developers.pipedrive.com/docs/api/v1>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 2.1 | primary_auth | oauth2 (also offers: api_key) | "You can create an app using either OAuth 2.0 (mandatory for all apps) or API token integration (private apps only)." — <https://pipedrive.readme.io/docs/about-the-marketplace><br>"The recommended authorization protocol for all public apps available in the Pipedrive Marketplace is the industry-standard OAuth 2.0 protocol." — <https://pipedrive.readme.io/docs/marketplace-oauth-api> |
| 2.2 | access_level | self_serve_trial | "Free 14-day trial. Full access. No credit card required." — <https://www.pipedrive.com/en/pricing><br>"You can get the API token manually from the Pipedrive web app by going to account name (on the top right) > Company settings > Personal preferences > API or by clicking here (in case you have multiple companies open at t" — <https://pipedrive.readme.io/docs/how-to-find-the-api-token> |
| 2.3 | mcp_status | official, unknown | "An official, reliable and fully supported connection built and maintained by Pipedrive." — <https://www.pipedrive.com/en/features/mcp-server> |
| 2.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/pipedrive |
| 2.5 | verdict | buildable_with_caveats (blocker: other) | follows from access and API coverage: A developer can obtain an API token during a 14-day trial and use the documented REST API. A developer sandbox is offered, but its price and approval requirements are not established, so the evidenced |

## 3. Zendesk (Support and Helpdesk)

API docs: <https://developer.zendesk.com/api-reference/>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 3.1 | primary_auth | oauth2 (also offers: api_key, basic) | "Zendesk supports using OAuth access tokens to authenticate API requests." — <https://developer.zendesk.com/api-reference/introduction/security-and-auth/><br>"If you plan on distributing an app, integration, or bot to multiple Zendesk customers, you must use global OAuth tokens to authenticate Zendesk API requests." — <https://developer.zendesk.com/api-reference/introduction/security-and-auth/> |
| 3.2 | access_level | self_serve_trial | "In this 10-minute quick start, you'll use the Zendesk Ticketing API to create a few tickets in Zendesk Support." — <https://developer.zendesk.com/documentation/ticketing/getting-started/zendesk-api-quick-start/><br>"To get a free account for testing, see Getting a trial or sponsored account for development ." — <https://developer.zendesk.com/documentation/ticketing/getting-started/zendesk-api-quick-start/> |
| 3.3 | mcp_status | community, generally_available | "A Model Context Protocol server for Zendesk. This server provides a comprehensive integration with Zendesk." — <https://github.com/reminia/zendesk-mcp-server><br>"The site includes an llms.txt file to help AI tools discover and use Zendesk developer documentation." — <https://developer.zendesk.com/api-reference/introduction/ai_tools/> |
| 3.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/zendesk |
| 3.5 | verdict | buildable_with_caveats (blocker: trial_only) | follows from access and API coverage: Zendesk documents a broad REST API and directs developers testing the Ticketing API to a free account identified as a 14-day trial. API availability generally follows the corresponding product feature |

## 4. Freshdesk (Support and Helpdesk)

API docs: <https://developers.freshdesk.com/api/>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 4.1 | primary_auth | api_key (also offers: basic) | "You can use your personal API key to authenticate the request. If you use the API key, there is no need for a password." — <https://developers.freshdesk.com/api/><br>"Irrespective of which version of Freshdesk's APIs you use, you will need to provide either your username and password combination or your API key for authorization when making API calls by triggering webhooks." — <https://support.freshdesk.com/support/solutions/articles/225435-where-can-i-find-my-api-key> |
| 4.2 | access_level | self_serve_trial | "How does the 14-day free trial work? When you sign up, you instantly get access to our Enterprise plan for 14 days. We will alert you before your trial expires. You can then select a plan and pay by credit card to contin" — <https://www.freshworks.com/freshdesk/pricing/><br>"Please note: For every trial period the API limit is 50 per minute." — <https://support.freshdesk.com/support/solutions/articles/225439-what-are-the-rate-limits-for-the-api-calls-to-freshdesk-> |
| 4.3 | mcp_status | official, generally_available | "The Freshworks Model Context Protocol (MCP) server enables AI tools like Cursor and Claude to securely connect and interact with Freshdesk." — <https://support.freshdesk.com/support/solutions/articles/50000012670-model-context-protocol-mcp-integration-in-freshdesk-eap-><br>"Starting September 10, 2026 , the Freshworks MCP integration is generally available." — <https://support.freshdesk.com/support/solutions/articles/50000012670-model-context-protocol-mcp-integration-in-freshdesk-eap-> |
| 4.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/freshdesk |
| 4.5 | verdict | buildable_with_caveats (blocker: trial_only) | follows from access and API coverage: A self-serve 14-day trial provides an API allowance, and the public REST API supports reading and writing helpdesk data. The free plan lacks API access, and continuing after the trial requires payment |

## 5. WhatsApp Business (Communications and Messaging)

API docs: <https://developers.facebook.com/documentation/business-messaging/whatsapp>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 5.1 | primary_auth | bearer_token (also offers: oauth2) | "If you are a direct developer, meaning only you or your business accesses your own data, use a System User access token." — <https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens><br>"When making API requests, include your token in an authorization request header, preceded by Bearer." — <https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens> |
| 5.2 | access_level | self_serve_free | "This guide helps developers quickly get started with the WhatsApp Cloud API. It covers the basic setup steps, including registering as a developer, creating a Meta app, sending your first message, and setting up a test w" — <https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started><br>"Test accounts and test phone numbers are useful for testing purposes, as they have relaxed messaging limits and don’t require a payment method on file in order to send template messages." — <https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform> |
| 5.3 | mcp_status | official, beta_or_pilot | "For developers building on the WhatsApp Business Platform (Cloud API) — the WhatsApp Business Tools MCP server lets your AI agent and IDE assistant manage and debug your WhatsApp Business integration from one place." — <https://developers.facebook.com/documentation/mcp/whatsapp-business-tools-mcp><br>"Note: The interface and tool set of the WhatsApp Business Tools MCP server are in beta and may change." — <https://developers.facebook.com/documentation/mcp/whatsapp-business-tools-mcp> |
| 5.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/whatsapp |
| 5.5 | verdict | buildable_now | follows from access and API coverage: A developer can register, create an app, and call the Cloud API with a generated token against an auto-provisioned test number that needs no payment method, and the public API covers messaging, templa |

## 6. Vonage (Communications and Messaging)

API docs: <https://developer.vonage.com/en/api>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 6.1 | primary_auth | bearer_token (also offers: api_key, basic, other) | "When you create a Vonage account, an API key and secret will be created for you. These are located in your account settings in the Vonage Dashboard." — <https://developer.vonage.com/getting-started/concepts/authentication><br>"A number of newer Vonage APIs require authentication to be done using an API key and secret sent Base64 encoded in the Authorization header." — <https://developer.vonage.com/getting-started/concepts/authentication> |
| 6.2 | access_level | self_serve_free | "To work with our APIs, you will need to sign up for an account . This will give you an API key and secret that you can use to access our APIs." — <https://developer.vonage.com/getting-started/overview><br>"Start developing now with free credit. No credit card required." — <https://www.vonage.com/communications-apis/pricing> |
| 6.3 | mcp_status | official, generally_available | "The Vonage Server API Bindings MCP Server , also known as the Tooling MCP Server, lets you invoke various API actions directly through your LLM Assistant or IDE of choice." — <https://developer.vonage.com/mcp-server/how-to-guides/install-tooling-mcp-server><br>"The MCP extension will automatically download and start the Vonage Tooling MCP Server ." — <https://developer.vonage.com/mcp-server/how-to-guides/install-tooling-mcp-server> |
| 6.4 | in_composio_catalog | no | none of the toolkit docs pages exists (404) |
| 6.5 | verdict | buildable_now | follows from access and API coverage: Self-serve signup yields API credentials and initial free credit. Public documentation covers communications, numbers, and application-management actions; API usage is charged per request. |

## 7. LinkedIn Ads (Marketing, Ads, Email and Social)

API docs: <https://learn.microsoft.com/en-us/linkedin/marketing/>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 7.1 | primary_auth | oauth2 | "All permissions listed are Member Permissions (3-legged OAuth), meaning they require an authenticated LinkedIn member to grant consent — your application requests these scopes during the OAuth authorization flow." — <https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access?view=li-lms-2026-11> |
| 7.2 | access_level | admin_approval | "The Advertising API, Community Management API, Events Management API, Lead Sync API, Conversions API, and Matched Audiences API are open to all approved developers — apply through the standard process." — <https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access?view=li-lms-2026-11><br>"All applications start with Development tier. You must apply separately to upgrade to the Standard tier." — <https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access?view=li-lms-2026-11> |
| 7.3 | mcp_status | community, generally_available | "This MCP server connects Claude Desktop (or any MCP-compatible client) to the LinkedIn Marketing API, allowing you to: Query campaign performance using natural language." — <https://github.com/danielpopamd/linkedin-ads-mcp> |
| 7.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/linkedin_ads |
| 7.5 | verdict | buildable_with_caveats (blocker: admin_approval) | follows from access and API coverage: The Marketing API is a documented, public REST API broad enough to create and manage campaigns, creatives, audiences and reporting via OAuth on a user's behalf, but credentials only work after LinkedI |

## 8. Pinterest (Marketing, Ads, Email and Social)

API docs: <https://developers.pinterest.com/docs/developer-tools/sandbox/>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 8.1 | primary_auth | oauth2 (also offers: bearer_token, basic) | "Make sure your API requests on a user"s behalf include a current access token that identifies the user and defines your permissions, or scopes, for using the API on their behalf." — <https://developers.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/><br>"Use HTTP Basic Authentication: Username: client_id Password: client_secret" — <https://developers.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/> |
| 8.2 | access_level | admin_approval | "If approved for API use, your app receives Trial access, which is best for exploring our API features." — <https://developers.pinterest.com/docs/key-concepts/access-tiers/><br>"Application requests are reviewed by Pinterest. You will receive an email notification after your app has been reviewed, letting you know whether it was approved or denied access." — <https://developers.pinterest.com/docs/getting-started/connect-app/> |
| 8.3 | mcp_status | community, generally_available | "After successful authentication, the MCP server will be ready to accept connections from AI agents." — <https://github.com/collactivelabs/pinterest-mcp-server/blob/main/README.md><br>"Be the first to know when it launches." — <https://developers.pinterest.com/about-pinterest-mcp> |
| 8.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/pinterest |
| 8.5 | verdict | buildable_with_caveats (blocker: admin_approval) | follows from access and API coverage: Pinterest documents a REST API with read/write capabilities, but app requests are reviewed before access is approved. Trial-created Pins and Boards are visible only to their creator, and Standard upgr |

## 9. Ecwid (Ecommerce)

API docs: <https://docs.ecwid.com/api-reference>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 9.1 | primary_auth | oauth2 (also offers: bearer_token) | "Ecwid uses OAuth 2.0 to provide secure access to the store data for public apps." — <https://docs.ecwid.com/get-started/make-your-first-api-request><br>"Add store ID to the request path , your secret access token as a Bearer Token on the Authorization tab , and click Send :" — <https://docs.ecwid.com/get-started/make-your-first-api-request> |
| 9.2 | access_level | admin_approval | "Only stores on paid plans can access API." — <https://docs.ecwid.com/get-started/set-up-your-dev-environment-in-ecwid><br>"Email us to get a free plan upgrade for your test store." — <https://docs.ecwid.com/get-started/set-up-your-dev-environment-in-ecwid> |
| 9.3 | mcp_status | community, generally_available | "Zapier Ecwid by Lightspeed MCP lets you connect Ecwid by Lightspeed 's actions with any AI tool that supports MCP, all without managing integrations or writing glue code." — <https://zapier.com/mcp/ecwid><br>"viaSocket MCP Server lets you easily connect Ecwid actions with AI tools like ChatGPT, Claude, and Cursor, all with built-in authentication." — <https://viasocket.com/mcp/ecwid-by-lightspeed> |
| 9.4 | in_composio_catalog | no | none of the toolkit docs pages exists (404) |
| 9.5 | verdict | buildable_with_caveats (blocker: admin_approval) | follows from access and API coverage: Ecwid's documented REST API supports reads and writes across core store data. A paid store provides immediate API access, but the no-cost route requires Ecwid to approve test-store access. |

## 10. Gumroad (Ecommerce)

API docs: <https://gumroad.com/api>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 10.1 | primary_auth | oauth2 (also offers: bearer_token) | "Gumroad's OAuth 2.0 API lets you see information about your products, as well as you can add, edit, and delete offer codes, variants, and custom fields." — <https://raw.githubusercontent.com/antiwork/gumroad/main/app/javascript/pages/Public/Api.tsx><br>"Redirect URI: For personal use, you can enter http://127.0.0.1 (localhost) as this value is not meaningful in this context." — <https://github.com/rmarescu/gumroad-mcp> |
| 10.2 | access_level | self_serve_free | "Log in to your Gumroad account (or your own instance of Gumroad). Go to Settings > Advanced page." — <https://github.com/rmarescu/gumroad-mcp><br>"Click "Create application." Use the "Generate access token" button to get your access token." — <https://github.com/rmarescu/gumroad-mcp> |
| 10.3 | mcp_status | official, generally_available | "Every assistant connects to its own URL and asks for OAuth access to your Gumroad account. Each connector page lists the exact address to paste." — <https://gumroad.com/mcp><br>"Listed in Claude’s connector directory. You can also add it as a custom connector." — <https://gumroad.com/claude> |
| 10.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/gumroad |
| 10.5 | verdict | buildable_now | follows from access and API coverage: Developers can generate a token for their own Gumroad account and use documented REST endpoints to read product and payout data and manage offer codes, variants, and custom fields. This verdict applie |

## 11. MrScraper (Data, SEO and Scraping)

API docs: <https://docs.mrscraper.com/docs/api/overview>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 11.1 | primary_auth | api_key (also offers: bearer_token) | "The MrScraper API uses API token authentication to secure all endpoints. Every request must include a valid API token in the HTTP request headers." — <https://docs.mrscraper.com/docs/api/authentication><br>"Keep Your Token Secure Your API token grants access to your account and plan resources." — <https://docs.mrscraper.com/docs/api/authentication> |
| 11.2 | access_level | self_serve_free | "The free tier gives you real credits to work with — not a 30-second demo or a single-page trial — which means you can genuinely validate your pipeline on your actual target sites." — <https://mrscraper.com/blog/free-web-scraping-apis><br>"What the free tier includes: Credits for real requests, AI extraction, Scraping Browser access, JavaScript rendering, and proxy rotation." — <https://mrscraper.com/blog/free-web-scraping-apis> |
| 11.3 | mcp_status | official, generally_available | "MrScraper MCP is the official Model Context Protocol server for MrScraper. It connects AI clients to web page retrieval, web search, and your account usage." — <https://docs.mrscraper.com/docs/getting-started/mcp-server><br>"Use the hosted Streamable HTTP endpoint for a managed connection, or run the published MCP package locally through Streamable HTTP or stdio." — <https://docs.mrscraper.com/docs/getting-started/mcp-server> |
| 11.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/mrscraper |
| 11.5 | verdict | buildable_now | follows from access and API coverage: A self-serve free account provides credits to test the documented REST API, which supports both direct extraction and repeatable scraper runs. Use the official MCP for page retrieval and search, and t |

## 12. Clay (Data, SEO and Scraping)

API docs: <https://developers.clay.com/>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 12.1 | primary_auth | api_key | "Every request to the Clay Public API must include a Clay API key in the clay-api-key header." — <https://developers.clay.com/public-api/authentication><br>"Clients that register themselves at connection time — a CLI connection like claude mcp add , or an editor such as Cursor or VS Code — aren't pre-verified by Clay, so the OAuth consent screen labels them Unverified applic" — <https://university.clay.com/docs/mcp-troubleshooting-and-faqs> |
| 12.2 | access_level | self_serve_free | "The developer platform is available across all Clay plans, including free, trial, and Legacy plans." — <https://university.clay.com/docs/clay-api-cli><br>"You can create an API key three ways: Ask your agent to generate one for you after installing the agent plugin . Run clay api-keys create --name "<key name>" with the clay CLI. The key is returned once, in the apiKey fie" — <https://developers.clay.com/quickstart> |
| 12.3 | mcp_status | official, generally_available | "MCP for Reps brings Clay's data and your team's approved workflows into the AI tools sellers already use, and the Clay Agent Plugin gives builders Clay's skills and the clay CLI inside their coding agent." — <https://university.clay.com/docs/mcp-for-reps-vs-agent-plugin><br>"Setup has two halves: an admin enables access, invites each rep, and sets their credit budget, and each rep then adds the connection in their own AI tool." — <https://university.clay.com/docs/mcp-for-reps-vs-agent-plugin> |
| 12.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/clay |
| 12.5 | verdict | buildable_now | follows from access and API coverage: The developer platform is available on the free plan, and the documented Public API supports searches and reusable Clay logic. Tables are Enterprise only. |

## 13. GitHub (Developer, Infra and Data platforms)

API docs: <https://docs.github.com/en/rest>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 13.1 | primary_auth | oauth2 (also offers: bearer_token, basic, none) | "If you want to use the API for an organization or on behalf of another user, GitHub recommends that you use a GitHub App." — <https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api><br>"If a user authorizes your app, your app can generate a user access token to make API requests on the user's behalf and attribute app activity to the user." — <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app> |
| 13.2 | access_level | self_serve_free | "You can register a GitHub App under your personal account or under any organization you own." — <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app><br>"GitHub offers free and paid plans for storing and collaborating on code." — <https://docs.github.com/en/get-started/learning-about-github/githubs-plans> |
| 13.3 | mcp_status | official, generally_available | "The GitHub MCP server is a Model Context Protocol (MCP) server provided and maintained by GitHub." — <https://docs.github.com/en/copilot/how-tos/copilot-in-your-ide/copilot-for-common-tasks/use-the-github-mcp-server><br>"The remote GitHub MCP server is hosted by GitHub and is the recommended option for most users." — <https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/set-up-the-github-mcp-server> |
| 13.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/github |
| 13.5 | verdict | buildable_now | follows from access and API coverage: A developer can register a GitHub App under a personal account and use the documented REST or GraphQL APIs. App permissions and organization approval policies may constrain access to particular resour |

## 14. Vercel (Developer, Infra and Data platforms)

API docs: <https://vercel.com/docs/rest-api>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 14.1 | primary_auth | oauth2 (also offers: bearer_token) | "Vercel's IdP uses the OAuth 2.0 authorization framework, a widely adopted industry standard for securing and delegating access to resources on behalf of users." — <https://vercel.com/docs/sign-in-with-vercel><br>"Access Token : A bearer token your application uses to call the Vercel REST API for the permissions the user grants. This lasts for 1 hour" — <https://vercel.com/docs/sign-in-with-vercel> |
| 14.2 | access_level | self_serve_free | "Your default team will be used when you make a request through the API or CLI and don’t specify a specific team." — <https://vercel.com/docs/accounts><br>"The first Hobby or Pro team you create will automatically be nominated as the default team." — <https://vercel.com/docs/accounts> |
| 14.3 | mcp_status | official, generally_available | "Vercel MCP is Vercel's official MCP server." — <https://vercel.com/docs/agent-resources/vercel-mcp><br>"Vercel MCP is available on all plans and your use is subject to Vercel's AI Product Terms ." — <https://vercel.com/docs/agent-resources/vercel-mcp> |
| 14.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/vercel |
| 14.5 | verdict | buildable_now | follows from access and API coverage: Vercel documents API requests against a default team that can be a free Hobby team, personal-account API-token creation, and a broad REST API. Submitting a Marketplace integration for review is distin |

## 15. Smartsheet (Productivity and Project Management)

API docs: <https://developers.smartsheet.com/api/smartsheet/introduction>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 15.1 | primary_auth | oauth2 (also offers: bearer_token) | "“If your scenario involves user consent and interaction, it's typically best to use OAuth with Smartsheet.”" — <https://developers.smartsheet.com/api/smartsheet/guides/basics/authentication><br>"“Each API request requires passing in an access token as the Bearer value in your authorization header.”" — <https://developers.smartsheet.com/api/smartsheet/guides/basics/authentication> |
| 15.2 | access_level | unknown | "“Required plan: Business, Enterprise, or Advanced Work Management Generate an API access token in the Smartsheet UI.”" — <https://developers.smartsheet.com/api/smartsheet/guides/getting-started><br>"“The email address used to register for Developer Tools must belong to an existing licensed Smartsheet user on a Business plan or higher.”" — <https://developers.smartsheet.com/register> |
| 15.3 | mcp_status | official, generally_available | "“With dozens of tools available at GA — spanning discovery, data retrieval, sheet creation, row and column operations, and collaboration — the MCP Server covers the workflows developers need from day one.”" — <https://www.smartsheet.com/content-center/product-insights/product-updates/introducing-smartsheet-mcp-server><br>"“Valid Smartsheet API token, unless you're connecting an AI tool that supports Smartsheet's OAuth, such as ChatGPT (web or mobile), Claude AI, Claude Desktop, Gemini Enterprise Plus, or Microsoft 365 Copilot.”" — <https://developers.smartsheet.com/ai-mcp/smartsheet/install-the-smartsheet-mcp-server> |
| 15.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/smartsheet |
| 15.5 | verdict | unknown (blocker: other) | follows from access and API coverage: The documented read/write REST API is broad enough to build a useful integration on a qualifying plan. It remains unverified whether a new developer can obtain working credentials through the public t |

## 16. Harvest (Productivity and Project Management)

API docs: <https://help.getharvest.com/api-v2/>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 16.1 | primary_auth | oauth2 (also offers: bearer_token) | "If you are interested in building integrations that other users can use, you will need to register an OAuth2 Application, also known as an OAuth2 Client." — <https://help.getharvest.com/api-v2/authentication-api/authentication/authentication/><br>"The API can be accessed by creating a Personal Access Token from the Developers section of Harvest ID." — <https://help.getharvest.com/api-v2/authentication-api/authentication/authentication/> |
| 16.2 | access_level | self_serve_free (inferred) | "Harvest does have a free version, and it is available for anyone to use, though it does have some limitations." — <https://support.getharvest.com/hc/en-us/articles/26145254105613-Is-there-a-free-version-of-Harvest><br>"The API can be accessed by creating a Personal Access Token from the Developers section of Harvest ID." — <https://help.getharvest.com/api-v2/authentication-api/authentication/authentication/> |
| 16.3 | mcp_status | official, generally_available | "The Harvest MCP is the connection that gives an MCP-compatible assistant — such as Claude — controlled access to your Harvest account, so it can carry out time tracking tasks on your behalf." — <https://support.getharvest.com/hc/en-us/articles/46293697226381-Harvest-MCP> |
| 16.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/harvest |
| 16.5 | verdict | buildable_now | follows from access and API coverage: Credentials are self-serve and free, and the documented API is broad enough to be useful. |

## 17. Stripe (Finance and Fintech)

API docs: <https://docs.stripe.com/api>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 17.1 | primary_auth | oauth2 (also offers: api_key, basic) | "The Stripe API authenticates requests using HTTP Basic Auth . Provide your API key as the basic auth username value." — <https://stripe.com/docs/api><br>"Use industry standard OAuth 2.0 to generate access tokens to interact with the Stripe API." — <https://docs.stripe.com/stripe-apps/api-authentication> |
| 17.2 | access_level | self_serve_free | "Immediately after you create a Stripe account, you can use a sandbox to simulate transactions and test Stripe features without moving any money. To accept real payments, you must set up your account ." — <https://docs.stripe.com/get-started/account><br>"Use the API keys page in the Dashboard to create, reveal, expire and rotate keys for the account or sandbox you’re viewing." — <https://docs.stripe.com/keys> |
| 17.3 | mcp_status | official, beta_or_pilot | "The Stripe Model Context Protocol (MCP) server provides tools that AI agents can use to interact with the Stripe API and search the Stripe knowledge base, including documentation and support articles." — <https://docs.stripe.com/mcp><br>"Before an agent completes certain actions on your behalf, Stripe can require you to review and approve the request in the Dashboard." — <https://docs.stripe.com/mcp> |
| 17.4 | in_composio_catalog | yes | https://docs.composio.dev/toolkits/stripe |
| 17.5 | verdict | buildable_now | follows from access and API coverage: Self-serve sandbox keys and a broad, public REST API are enough to build and test a useful toolkit now. The official MCP server’s preview status does not block a direct API integration. |

## 18. Binance (Finance and Fintech)

API docs: <https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/rest-api.md>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 18.1 | primary_auth | api_key (also offers: none) | "Secure endpoints require a valid API key to be specified and authenticated." — <https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/rest-api.md><br>"If unspecified, the security type is `NONE`." — <https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/rest-api.md> |
| 18.2 | access_level | self_serve_free | "Step 1: Log in on this website, and generate an API Key." — <https://testnet.binance.vision/><br>"All users registering on the Spot Test Network automatically receive a balance in many different assets." — <https://testnet.binance.vision/> |
| 18.3 | mcp_status | official, generally_available | "Connect your AI agent to Binance with a single URL. Your agent can read market data, check balances, trade Spot / Margin / Convert / USDⓈ-M / COIN-M Futures, and move funds between wallets inside a dedicated Agentic sub-" — <https://developers.binance.com/en/docs/agent-native/mcp-server/agentic><br>"A Binance Spot MCP server for compatible AI clients, using stdio and ten tools. Node.js 24+ is required." — <https://github.com/ethancod1ng/binance-mcp-server> |
| 18.4 | in_composio_catalog | no | none of the toolkit docs pages exists (404) |
| 18.5 | verdict | buildable_now | follows from access and API coverage: Developers can generate Spot Test Network API keys, and the public Spot API documents account reads and order placement. The test network supports only /api endpoints, and trading must be enabled sepa |

## 19. Reducto (AI, Research and Media-native)

API docs: <https://docs.reducto.ai/api-reference/api/sections/parse/operations/parse>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 19.1 | primary_auth | api_key (also offers: oauth2) | "Create an API key in Reducto Studio (https://studio.reducto.ai) under API Keys. Signed-in readers can create one on this page." — <https://docs.reducto.ai/quickstart/index.md><br>"The token exchange endpoint trades a subject token from your identity provider for a short-lived Reducto access token. It implements [OAuth 2.0 Token Exchange (RFC 8693)](https://datatracker.ietf.org/doc/html/rfc8693)." — <https://docs.reducto.ai/security/workload-identity-federation/reference/index.md> |
| 19.2 | access_level | self_serve_free | "Sign up for a free account without leaving the docs." — <https://docs.reducto.ai/quickstart><br>"Sign in to create a key here, or create one in Studio under API Keys." — <https://docs.reducto.ai/quickstart> |
| 19.3 | mcp_status | official, generally_available | "The Reducto MCP server connects AI agents directly to Reducto. Once installed, agents in Claude Desktop, Claude Code, Codex, Cursor, VS Code, Windsurf, or any other [Model Context Protocol](https://modelcontextprotocol.i" — <https://docs.reducto.ai/mcp-server/index.md><br>"The hosted server (mcp.reducto.ai) does not support local paths. Use a public URL or run the server locally." — <https://docs.reducto.ai/mcp-server/index.md> |
| 19.4 | in_composio_catalog | no | none of the toolkit docs pages exists (404) |
| 19.5 | verdict | buildable_now | follows from access and API coverage: Developers can create a free account and generate an API key without contacting sales. The public REST API covers the core document workflow, and Reducto offers an official MCP server for direct agent |

## 20. Mermaid CLI (AI, Research and Media-native)

API docs: <https://github.com/mermaid-js/mermaid-cli>

| # | Field | Agent's answer | Evidence to check |
|---|---|---|---|
| 20.1 | primary_auth | none | "It's possible to call mermaid-cli via a Node.JS API. Please be aware that the NodeJS API is not covered by semver , as mermaid-cli follows mermaid 's versioning." — <https://github.com/mermaid-js/mermaid-cli><br>"You can easily pipe input from stdin. This example shows how to use a heredoc to send a diagram as stdin to mermaid-cli (mmdc)." — <https://github.com/mermaid-js/mermaid-cli> |
| 20.2 | access_level | self_serve_free (inferred) | "Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation" — <https://github.com/mermaid-js/mermaid-cli/blob/master/LICENSE> |
| 20.3 | mcp_status | community, generally_available | "The server internally calls npx @mermaid-js/mermaid-cli as a subprocess to perform diagram validation and rendering." — <https://github.com/andrewginns/mermaid-mcp-server> |
| 20.4 | in_composio_catalog | no | none of the toolkit docs pages exists (404) |
| 20.5 | verdict | buildable_with_caveats (blocker: narrow_api) | follows from access and API coverage: Credentials are self-serve, but the API is narrow. |
