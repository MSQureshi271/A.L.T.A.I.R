> ## Documentation Index
> Fetch the complete documentation index at: https://developers.notion.com/llms.txt
> Use this file to discover all available pages before exploring further.

> Insert or replace content in a page using enhanced markdown.

# Update a page's content as markdown

export const developerConnectionsUrl = "https://app.notion.com/developers/connections";

### Use cases

#### Updating content with search-and-replace (recommended)

Use the `update_content` command to make targeted edits using an array of search-and-replace operations. Each operation specifies an `old_str` to find and a `new_str` to replace it with. This is the recommended approach for making precise edits without rewriting the full page.

#### Replacing all page content (recommended)

Use the `replace_content` command to replace the entire page content with new markdown. Provide the full replacement content in `new_str`.

#### Inserting content (legacy)

Use the `insert_content` command to add new markdown content to a page. Provide `position: { "type": "start" }` to prepend, `position: { "type": "end" }` to explicitly append, or omit `position` to append to the end of the page. You can also provide an `after` selection to insert at a specific point; `after` uses an **ellipsis-based selection** format: `"start text...end text"`.

<Note>
  We recommend using `update_content` or `replace_content` instead. The `insert_content` command is still supported but may be deprecated in a future version.
</Note>

#### Replacing a content range (legacy)

Use the `replace_content_range` command to replace a matched range of existing content with new markdown. The `content_range` parameter uses the same ellipsis-based selection format as `after`.

<Note>
  We recommend using `update_content` instead. The `replace_content_range` command is still supported but may be deprecated in a future version.
</Note>

### General behavior

Returns a `page_markdown` object containing the full page content as enhanced markdown after the update, including `truncated` and `unknown_block_ids` fields for large pages.

Set `allow_async: true` at the top level of the request body to receive an HTTP `202` response with an `async_task` object instead of waiting for the markdown update to finish in the original request. This is useful for high block-count markdown updates, especially `replace_content` requests and large batches of `update_content` operations.

If `allow_async` is omitted or `false`, this endpoint keeps its existing synchronous response behavior. `allow_async` changes response behavior only; it does not change validation, permissions, or which operation runs. See [Retrieve an async task](/reference/retrieve-async-task) and [Working with markdown content](/guides/data-apis/working-with-markdown-content#running-large-markdown-writes-asynchronously) for polling examples.

<Info>
  **Requirements**

  Your connection must have [update content capabilities](/reference/capabilities#content-capabilities) on the target page in order to call this endpoint. To update your connection's capabilities, navigate to the <a href={developerConnectionsUrl}>Developer portal</a>, select your connection, open the **Configuration** tab, and scroll to the Capabilities section.

  Attempting to call this endpoint without update content capabilities returns an HTTP response with a 403 status code.
</Info>

<Tip>
  **Newlines in content**

  The `content` field expects standard markdown with actual newline characters. In JSON, `\n` is the escape sequence for a newline — for example, `"## Heading\n\nParagraph"` creates a heading followed by a paragraph.

  When using cURL, wrap the `--data` body in **single quotes** (`'...'`) so that `\n` is passed through to the JSON parser. Avoid `$'...'` quoting, which converts `\n` into a literal newline and produces invalid JSON.

  Note that the interactive API explorer on this page does not support multiline input. To test with newlines, use cURL, an SDK, or any HTTP client that sends properly encoded JSON.
</Tip>

<Warning>
  **Protecting child pages and databases**

  By default, this endpoint refuses to delete child pages or databases. If an operation would remove them, a `validation_error` is returned listing the affected items. Set `allow_deleting_content` to `true` in the command body (`replace_content_range`, `update_content`, or `replace_content`) to permit deletion.
</Warning>

### Errors

| Error code         | Condition                                                                                                                          |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| `validation_error` | The `content_range` or `after` selection does not match any content in the page, or an `old_str` in `update_content` is not found. |
| `validation_error` | Both `insert_content.after` and `insert_content.position` are provided. Use only one insertion target.                             |
| `validation_error` | The operation would delete child pages or databases and `allow_deleting_content` is not `true`.                                    |
| `validation_error` | An `old_str` in `update_content` matches multiple locations and `replace_all_matches` is not `true`.                               |
| `validation_error` | The provided ID is a database or non-page block.                                                                                   |
| `validation_error` | The target page is a synced page. Synced pages cannot be updated.                                                                  |
| `object_not_found` | The page does not exist or the connection does not have access to it.                                                              |

*Each Public API endpoint can return several possible error codes. See the [Error codes section](/reference/status-codes#error-codes) of the Status codes documentation for more information.*


## OpenAPI

````yaml patch /v1/pages/{page_id}/markdown
openapi: 3.1.0
info:
  title: Notion API
  version: 1.0.0
  termsOfService: >-
    https://notion.notion.site/Terms-and-Privacy-28ffdd083dc3473e9c2da6ec011b58ac
servers:
  - url: https://api.notion.com
security:
  - bearerAuth: []
tags:
  - name: Databases
    description: Database endpoints
  - name: Data sources
    description: Data source endpoints
  - name: Pages
    description: Page endpoints
  - name: Async tasks
    description: Async task endpoints
  - name: Blocks
    description: Block endpoints
  - name: Comments
    description: Comment endpoints
  - name: File uploads
    description: File upload endpoints
  - name: OAuth
    description: OAuth endpoints (basic authentication)
  - name: Users
    description: User endpoints
  - name: Search
    description: Search endpoints
  - name: Views
    description: View endpoints
  - name: Custom emojis
    description: Custom emoji endpoints
  - name: Meeting notes
    description: Meeting notes endpoints
paths:
  /v1/pages/{page_id}/markdown:
    patch:
      tags:
        - Pages
      summary: Update a page's content as markdown
      operationId: update-page-markdown
      parameters:
        - name: page_id
          in: path
          required: true
          schema:
            $ref: '#/components/schemas/idRequest'
            description: The ID of the page to update.
        - $ref: '#/components/parameters/notionVersion'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              allOf:
                - type: object
                  properties:
                    allow_async:
                      type: boolean
                      description: >-
                        Set to true to opt into receiving an async_task result
                        when this update operation is accepted for background
                        execution. If omitted or false, the endpoint keeps the
                        existing synchronous response shape.
                - oneOf:
                    - type: object
                      properties:
                        type:
                          type: string
                          const: insert_content
                          description: Always `insert_content`
                        insert_content:
                          type: object
                          properties:
                            content:
                              type: string
                              examples:
                                - |-
                                  ## New Section

                                  Inserted content here.
                              description: >-
                                The enhanced markdown content to insert into the
                                page.
                            after:
                              type: string
                              description: >-
                                Selection of existing content to insert after,
                                using the ellipsis format ("start text...end
                                text"). Omit to append at the end of the page.
                            position:
                              oneOf:
                                - type: object
                                  properties:
                                    type:
                                      type: string
                                      const: start
                                      description: >-
                                        Insert the content at the start of the
                                        page.
                                  required:
                                    - type
                                - type: object
                                  properties:
                                    type:
                                      type: string
                                      const: end
                                      description: >-
                                        Insert the content at the end of the
                                        page.
                                  required:
                                    - type
                              description: >-
                                Explicit position for inserted content. Use
                                {"type":"start"} to prepend or {"type":"end"} to
                                append. Cannot be combined with after.
                          required:
                            - content
                          description: Insert new content into the page.
                      required:
                        - type
                        - insert_content
                      title: Insert Content
                      deprecated: true
                    - type: object
                      properties:
                        type:
                          type: string
                          const: replace_content_range
                          description: Always `replace_content_range`
                        replace_content_range:
                          type: object
                          properties:
                            content:
                              type: string
                              examples:
                                - |-
                                  ## Updated Section

                                  New content replaces the old.
                              description: >-
                                The new enhanced markdown content to replace the
                                matched range.
                            content_range:
                              type: string
                              description: >-
                                Selection of existing content to replace, using
                                the ellipsis format ("start text...end text").
                            allow_deleting_content:
                              type: boolean
                              description: >-
                                Set to true to allow the operation to delete
                                child pages or databases. Defaults to false.
                          required:
                            - content
                            - content_range
                          description: Replace a range of content in the page.
                      required:
                        - type
                        - replace_content_range
                      title: Replace Content Range
                      deprecated: true
                    - type: object
                      properties:
                        type:
                          type: string
                          const: update_content
                          description: Always `update_content`
                        update_content:
                          type: object
                          properties:
                            content_updates:
                              type: array
                              items:
                                type: object
                                properties:
                                  old_str:
                                    type: string
                                    description: >-
                                      The existing content string to find and
                                      replace. Must exactly match the page
                                      content.
                                  new_str:
                                    type: string
                                    description: >-
                                      The new content string to replace old_str
                                      with.
                                  replace_all_matches:
                                    type: boolean
                                    description: >-
                                      If true, replaces all occurrences of
                                      old_str. If false (default), the operation
                                      fails if there are multiple matches.
                                required:
                                  - old_str
                                  - new_str
                              maxItems: 100
                              description: >-
                                An array of search-and-replace operations, each
                                with old_str (content to find) and new_str
                                (replacement content).
                            allow_deleting_content:
                              type: boolean
                              description: >-
                                Set to true to allow the operation to delete
                                child pages or databases. Defaults to false.
                          required:
                            - content_updates
                          description: >-
                            Update specific content using search-and-replace
                            operations.
                      required:
                        - type
                        - update_content
                      title: Update Content
                    - type: object
                      properties:
                        type:
                          type: string
                          const: replace_content
                          description: Always `replace_content`
                        replace_content:
                          type: object
                          properties:
                            new_str:
                              type: string
                              examples:
                                - |-
                                  # Updated Page

                                  Completely new page content.
                              description: >-
                                The new enhanced markdown content to replace the
                                entire page content.
                            allow_deleting_content:
                              type: boolean
                              description: >-
                                Set to true to allow the operation to delete
                                child pages or databases. Defaults to false.
                          required:
                            - new_str
                          description: Replace the entire page content with new markdown.
                      required:
                        - type
                        - replace_content
                      title: Replace Content
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/pageMarkdownResponse'
        '202':
          description: >-
            Accepted when `allow_async` is true and the update has been queued
            for background execution.
          content:
            application/json:
              schema:
                type: object
                additionalProperties: false
                required:
                  - object
                  - id
                  - status
                  - status_url
                  - created_time
                  - poll_after_seconds
                  - operation
                properties:
                  object:
                    type: string
                    enum:
                      - async_task
                  id:
                    type: string
                    minLength: 1
                  status:
                    type: string
                    enum:
                      - queued
                      - running
                      - retrying
                  status_url:
                    type: string
                    minLength: 1
                  created_time:
                    type: string
                    format: date-time
                  poll_after_seconds:
                    type: integer
                    minimum: 0
                  operation:
                    oneOf:
                      - type: object
                        additionalProperties: false
                        required:
                          - surface
                          - name
                        properties:
                          surface:
                            type: string
                            enum:
                              - rest
                          name:
                            type: string
                            enum:
                              - PATCH /v1/pages/:page_id/markdown
                      - type: object
                        additionalProperties: false
                        required:
                          - surface
                          - name
                        properties:
                          surface:
                            type: string
                            enum:
                              - mcp
                          name:
                            type: string
                            enum:
                              - create_pages
        '400':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_400'
        '401':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_401'
        '403':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_403'
        '404':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_404'
        '406':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_406'
        '409':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_409'
        '429':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_429'
        '500':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_500'
        '503':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_503'
        '504':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_504'
        '529':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/error_api_529'
      x-codeSamples:
        - lang: javascript
          label: TypeScript SDK
          source: |-
            import { Client } from "@notionhq/client"

            const notion = new Client({ auth: process.env.NOTION_API_KEY })

            const response = await notion.pages.updateMarkdown({
              page_id: "b55c9c91-384d-452b-81db-d1ef79372b75",
              type: "update_content",
              update_content: {
                content_updates: [
                  {
                    old_str: "existing text to find",
                    new_str: "replacement text"
                  }
                ]
              }
            })
components:
  schemas:
    idRequest:
      type: string
    pageMarkdownResponse:
      type: object
      properties:
        object:
          type: string
          const: page_markdown
          description: The type of object, always 'page_markdown'.
        id:
          $ref: '#/components/schemas/idResponse'
          description: The ID of the page or block.
        markdown:
          type: string
          description: The page content rendered as enhanced Markdown.
        truncated:
          type: boolean
          description: >-
            Whether the content was truncated due to exceeding the record count
            limit.
        unknown_block_ids:
          type: array
          items:
            $ref: '#/components/schemas/idResponse'
          maxItems: 100
          description: >-
            Block IDs that could not be loaded (appeared as <unknown> tags in
            the markdown). Pass these IDs back to this endpoint to fetch their
            content separately.
      additionalProperties: false
      required:
        - object
        - id
        - markdown
        - truncated
        - unknown_block_ids
    error_api_400:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - invalid_json
                - invalid_request_url
                - invalid_request
                - missing_version
                - validation_error
            status:
              const: 400
          required:
            - code
            - status
          additionalProperties: false
    error_api_401:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - unauthorized
            status:
              const: 401
          required:
            - code
            - status
          additionalProperties: false
    error_api_403:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - restricted_resource
                - status_change_not_allowed
            status:
              const: 403
          required:
            - code
            - status
          additionalProperties: false
    error_api_404:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - object_not_found
                - directory_not_found
            status:
              const: 404
          required:
            - code
            - status
          additionalProperties: false
    error_api_406:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - row_limit_exceeded
            status:
              const: 406
          required:
            - code
            - status
          additionalProperties: false
    error_api_409:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - conflict_error
                - agent_deleted
            status:
              const: 409
          required:
            - code
            - status
          additionalProperties: false
    error_api_429:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - rate_limited
            status:
              const: 429
          required:
            - code
            - status
          additionalProperties: false
    error_api_500:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - internal_server_error
            status:
              const: 500
          required:
            - code
            - status
          additionalProperties: false
    error_api_503:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - service_unavailable
            status:
              const: 503
          required:
            - code
            - status
          additionalProperties: false
    error_api_504:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - gateway_timeout
            status:
              const: 504
          required:
            - code
            - status
          additionalProperties: false
    error_api_529:
      allOf:
        - $ref: '#/components/schemas/publicApiCommonErrorResponse'
        - type: object
          properties:
            code:
              enum:
                - service_overload
            status:
              const: 529
          required:
            - code
            - status
          additionalProperties: false
    idResponse:
      type: string
      format: uuid
    publicApiCommonErrorResponse:
      type: object
      properties:
        object:
          const: error
        message:
          type: string
        additional_data:
          type: object
          additionalProperties:
            oneOf:
              - type: string
              - type: array
                items:
                  type: string
      required:
        - object
        - message
  parameters:
    notionVersion:
      name: Notion-Version
      in: header
      required: true
      schema:
        enum:
          - '2026-03-11'
      description: >-
        The [API version](/reference/versioning) to use for this request. The
        latest version is `2026-03-11`.
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer

````