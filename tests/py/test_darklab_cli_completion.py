# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from darklab_cli_test_support import load_cli_main


def test_darklab_cli_help_and_completion_contract(monkeypatch, capsys, tmp_path):
    cli_main = load_cli_main()
    help_text = cli_main._parser().format_help()
    assert "active            List active runs for the current token." in help_text
    assert "completion        Print or install shell completion for bash, zsh, or" in help_text
    assert "fish." in help_text
    assert "download          Download one artifact by id." in help_text
    assert "advisory          Run explicit advisory lookups; ordinary reads never" in help_text
    assert "evidence          Read and manage typed evidence without copying" in help_text
    assert "finding           Create and edit assessor-authored Project findings." in help_text
    assert "http-profile      Read and manage Project HTTP profiles without" in help_text
    assert "risk              Read configured CVE risk feed state without starting" in help_text
    assert "commands:" not in help_text
    assert cli_main.main(["completion", "bash"]) == 0
    bash_completion = capsys.readouterr().out
    assert "complete -F _darklab_completion darklab" in bash_completion
    assert (
        "active advisory artifacts assessment atlas cancel completion download "
        "evidence finding grep history http-profile notify"
    ) in bash_completion
    assert (
        "assessment) _darklab_comp_words 'archive batch checks clear-state complete "
        "create delete list set-state show start-action'"
    ) in bash_completion
    assert "assessment:create:--format) _darklab_comp_words 'text json'; return ;;" in bash_completion
    assert "advisory) _darklab_comp_words osv" in bash_completion
    assert "advisory:osv) _darklab_comp_words '--format --help -h'" in bash_completion
    assert "advisory:osv:--format) _darklab_comp_words 'text json'; return ;;" in bash_completion
    assert "evidence) _darklab_comp_words 'link list services unlink'" in bash_completion
    assert "finding) _darklab_comp_words 'create edit'" in bash_completion
    assert "http-profile) _darklab_comp_words 'create delete list show update'" in bash_completion
    assert "evidence:link:--format) _darklab_comp_words 'text json'; return ;;" in bash_completion
    assert "evidence:list:--format) _darklab_comp_words 'text json ndjson'; return ;;" in bash_completion
    assert "risk) _darklab_comp_words status" in bash_completion
    assert "assessment:batch) _darklab_comp_words 'cancel follow list plan retry show start'" in bash_completion
    assert "atlas) _darklab_comp_words 'entities entity finding findings runs summary'" in bash_completion
    assert "team:invite) _darklab_word_in \"$word\" 'create revoke'" in bash_completion
    invite_create_completion = (
        "team:invite:create) _darklab_comp_words '--expires-at --format --help --label --max-uses --role -h'"
    )
    assert invite_create_completion in bash_completion
    assert "run:--format) _darklab_comp_words 'text json ndjson'; return ;;" in bash_completion
    assert "team:invite:create:--role) _darklab_comp_words 'owner admin operator viewer'; return ;;" in bash_completion
    assert "notify:create) _darklab_comp_words 'webhook slack discord telegram pushover email'" in bash_completion
    assert cli_main.main(["completion", "zsh"]) == 0
    zsh_completion = capsys.readouterr().out
    assert "#compdef darklab" in zsh_completion
    assert "team:invite) _darklab_word_in \"$word\" 'create revoke'" in zsh_completion
    assert "team:invite:create) _darklab_comp_words '--expires-at --format --help --label --max-uses --role -h'" in zsh_completion
    assert "compdef _darklab darklab" in zsh_completion
    assert cli_main.main(["completion", "fish"]) == 0
    fish_completion = capsys.readouterr().out
    assert "complete -c darklab -f -n '__fish_use_subcommand'" in fish_completion
    assert "-a 'webhook slack discord telegram pushover email'" in fish_completion
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert cli_main.main(["completion", "install"]) == 0
    install_output = capsys.readouterr().out
    bash_completion_path = tmp_path / "data" / "bash-completion" / "completions" / "darklab"
    assert f"Installed bash completion to {bash_completion_path}" in install_output
    assert "complete -F _darklab_completion darklab" in bash_completion_path.read_text(encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert cli_main.main(["completion", "install", "--shell", "fish"]) == 0
    fish_completion_path = tmp_path / "config" / "fish" / "completions" / "darklab.fish"
    assert f"Installed fish completion to {fish_completion_path}" in capsys.readouterr().out
    assert "complete -c darklab -f" in fish_completion_path.read_text(encoding="utf-8")
