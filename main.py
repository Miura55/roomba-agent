from __future__ import annotations

import asyncio

import streamlit as st
from mcp.client.stdio import StdioServerParameters, stdio_client
from strands import Agent
from strands.agent.agent_result import AgentResult
from strands.models.ollama import OllamaModel
from strands.tools.mcp.mcp_client import MCPClient


SYSTEM_PROMPT = """
あなたはルンバ操縦用のAIエージェントです。必ずMCPツールを使って実機を操作してください。

基本方針:
- ユーザーへの返答は日本語で、短く明確に行う
- 実行前に「これから何を実行するか」を1行で伝える
- 危険な経路が想定される場合は、短く注意喚起してから実行する

moveツールの厳密ルール:
- velocity は m/s、yaw_rate は deg/s、duration は秒で指定する
- velocity は小数を許容する
- duration の指定がない場合は 1 を使う
- 直進・後進では yaw_rate = 0 とし、velocity の符号で前後を表す
- 旋回では velocity = 0 とし、yaw_rate の符号で左右を表す

自然言語の解釈ルール:
- 「前に進んで」「下がって」など距離指定が曖昧な場合は、まずメートル単位で確認する
- 「少し左に回って」など角度指定が曖昧な場合は、まず度数で確認する
- ユーザーが距離や角度を指定した場合は、採用した速度または角速度から duration を計算して move を呼ぶ
- 「ホームに戻る」の意図なら、対応ツールを即時実行する
""".strip()

SIDEBAR_CANDIDATES = [
    "0.20m/sで3秒まっすぐ前進してください",
    "0.15m/sで2秒だけ後ろに下がってください",
    "その場で左に回転して。角速度は45deg/sで2秒",
    "その場で右に回転して。角速度は-45deg/sで2秒",
    "掃除をやめてホームに戻ってください",
]

OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL_ID = "gemma4:e2b"


def _extract_text(result: AgentResult) -> str:
    """Extract readable assistant text from Strands AgentResult."""
    text_blocks: list[str] = []

    for block in result.message.get("content", []):
        text = block.get("text")
        if text:
            text_blocks.append(text)

    if text_blocks:
        return "\n".join(text_blocks).strip()

    return "応答テキストを取得できませんでした。"


def _extract_tool_names(result: AgentResult) -> list[str]:
    """Extract called tool names from Strands AgentResult."""
    tool_names: list[str] = []

    for block in result.message.get("content", []):
        tool_use = block.get("toolUse")
        tool_name = tool_use.get("name") if tool_use else None
        if tool_name and tool_name not in tool_names:
            tool_names.append(tool_name)

    return tool_names


@st.cache_resource(show_spinner=False)
def _build_agent() -> tuple[MCPClient, Agent]:
    """Create and cache MCP connection + Strands agent for Streamlit reruns."""
    ollama_model = OllamaModel(
        host=OLLAMA_HOST,
        model_id=OLLAMA_MODEL_ID,
    )

    server_params = StdioServerParameters(
        command="uvx",
        args=["mcp-proxy", "http://localhost:8000/mcp"],
    )
    mcp_client = MCPClient(lambda: stdio_client(server_params))

    agent = Agent(
        model=ollama_model,
        tools=[mcp_client],
        system_prompt=SYSTEM_PROMPT,
    )
    return mcp_client, agent


def _initialize_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []


def _run_agent_streaming(
    agent: Agent,
    prompt: str,
    text_placeholder: object,
    tool_placeholder: object,
) -> tuple[str, list[str]]:
    streamed_chunks: list[str] = []
    streamed_tool_names: list[str] = []

    def _refresh_tool_placeholder() -> None:
        if streamed_tool_names:
            tool_placeholder.caption(f"呼び出しツール: {', '.join(streamed_tool_names)}")
        else:
            tool_placeholder.empty()

    def _capture_tool_name(name: object) -> None:
        if isinstance(name, str) and name and name not in streamed_tool_names:
            streamed_tool_names.append(name)
            _refresh_tool_placeholder()

    async def _consume_stream() -> AgentResult:
        final_result: AgentResult | None = None

        async for stream_event in agent.stream_async(prompt):
            data = stream_event.get("data") if isinstance(stream_event, dict) else None
            if isinstance(data, str) and data:
                streamed_chunks.append(data)
                text_placeholder.markdown("".join(streamed_chunks))

            if isinstance(stream_event, dict):
                raw_event = stream_event.get("event")
                if isinstance(raw_event, dict):
                    content_block_start = raw_event.get("contentBlockStart")
                    if isinstance(content_block_start, dict):
                        start = content_block_start.get("start")
                        if isinstance(start, dict):
                            tool_use = start.get("toolUse")
                            if isinstance(tool_use, dict):
                                _capture_tool_name(tool_use.get("name"))

                current_tool_use = stream_event.get("current_tool_use")
                if isinstance(current_tool_use, dict):
                    _capture_tool_name(current_tool_use.get("name"))

                result = stream_event.get("result")
                if isinstance(result, AgentResult):
                    final_result = result

        if final_result is None:
            final_result = agent(prompt)
        return final_result

    with st.spinner("ルンバに指示しています..."):
        result = asyncio.run(_consume_stream())

    result_tool_names = _extract_tool_names(result)
    for tool_name in result_tool_names:
        if tool_name not in streamed_tool_names:
            streamed_tool_names.append(tool_name)

    _refresh_tool_placeholder()

    answer = "".join(streamed_chunks).strip()
    if not answer:
        answer = _extract_text(result)
        text_placeholder.markdown(answer)

    return answer, streamed_tool_names


def _render_chat_message(message: dict[str, object]) -> None:
    tool_names = message.get("tool_names")
    if isinstance(tool_names, list) and tool_names:
        st.caption(f"呼び出しツール: {', '.join(str(name) for name in tool_names)}")

    content = message.get("content", "")
    st.markdown(str(content))


def _format_tool_entry(tool: object) -> str:
    """Render a readable label for MCP tools returned by Strands."""
    tool_name = getattr(tool, "tool_name", None) or getattr(tool, "name", None)
    description = None

    tool_spec = getattr(tool, "tool_spec", None)
    if callable(tool_spec):
        try:
            spec = tool_spec()
            description = spec.get("description") if isinstance(spec, dict) else None
        except Exception:  # noqa: BLE001  # pragma: no cover - best effort UI rendering
            description = None
    elif isinstance(tool_spec, dict):
        description = tool_spec.get("description")

    return f"- **{tool_name or 'unknown'}**: {description or '(descriptionなし)'}"


def main() -> None:
    st.set_page_config(page_title="Roomba Agent", page_icon="🤖", layout="wide")
    st.title("Roomba MCP Agent")
    st.caption("MCP (stdio) 経由でルンバを操作するAIエージェント")

    _initialize_state()

    try:
        mcp_client, agent = _build_agent()
    except Exception as exc:  # noqa: BLE001  # pragma: no cover - runtime environment dependent
        st.error("MCP接続の初期化に失敗しました。")
        st.exception(exc)
        return

    with st.sidebar:
        st.subheader("質問候補")
        st.write("下の候補を押すと、そのままチャット入力として送信できます。")

        selected_prompt = ""
        for candidate in SIDEBAR_CANDIDATES:
            if st.button(candidate, use_container_width=True):
                selected_prompt = candidate

        with st.expander("利用可能なMCPツール", expanded=False):
            try:
                tools = mcp_client.list_tools_sync()
                if not tools:
                    st.info("MCPツールが見つかりませんでした。")
                else:
                    for tool in tools:
                        st.markdown(_format_tool_entry(tool))
            except Exception as exc:  # noqa: BLE001  # pragma: no cover - runtime environment dependent
                st.warning(f"MCPツール一覧の取得に失敗しました: {exc}")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            _render_chat_message(message)

    typed_prompt = st.chat_input("例: 0.2m/sで3秒前進して")
    prompt = selected_prompt or typed_prompt

    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        _render_chat_message({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        tool_placeholder = st.empty()
        text_placeholder = st.empty()

        try:
            answer, tool_names = _run_agent_streaming(
                agent,
                prompt,
                text_placeholder=text_placeholder,
                tool_placeholder=tool_placeholder,
            )
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - runtime environment dependent
            answer = f"エージェント実行中にエラーが発生しました: {exc}"
            tool_names = []
            tool_placeholder.empty()
            text_placeholder.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer, "tool_names": tool_names})


if __name__ == "__main__":
    main()
