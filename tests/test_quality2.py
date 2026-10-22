"""Quality pass 2 (22-oct-2026): music ducked under the voices with a limiter on the sum."""
import short_kit as kit


def test_the_bed_is_ducked_under_the_voices_and_the_sum_limited(monkeypatch):
    monkeypatch.delenv("MUSIC_DUCK", raising=False)
    graph = []
    kit._final_mix(graph, ["[0:a]", "[bed]", "[vo0]", "[vo1]", "[sx0]"])
    text = ";".join(graph)
    assert "[vo0][vo1]amix=inputs=2:normalize=0,asplit=2[vox][vkey]" in text
    assert "[bed][vkey]sidechaincompress" in text
    assert graph[-1].startswith("[0:a][sx0][vox][bedd]amix=inputs=4:duration=first") and "alimiter" in graph[-1]


def test_no_bed_or_switched_off_is_the_plain_sum(monkeypatch):
    graph = []
    kit._final_mix(graph, ["[0:a]", "[vo0]"])
    assert graph == ["[0:a][vo0]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0[a]"]
    monkeypatch.setenv("MUSIC_DUCK", "0")
    graph = []
    kit._final_mix(graph, ["[0:a]", "[bed]", "[vo0]"])
    assert "sidechaincompress" not in ";".join(graph)
    graph = []
    kit._final_mix(graph, ["[1:a]"])
    assert graph == ["[1:a]anull[a]"]
