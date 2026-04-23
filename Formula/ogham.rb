class Ogham < Formula
  include Language::Python::Virtualenv

  desc "Minimal in-terminal chat app built with Textual"
  homepage "https://github.com/JRiggles/ogham-chat"
  license "MIT"
  head "https://github.com/JRiggles/ogham-chat.git", branch: "main"

  depends_on "python@3.12"

  def install
    venv = virtualenv_create(libexec, "python3.12")
    venv.pip_install %w[
      fastapi[standard]>=0.135.3
      psycopg[binary]>=3.2.9
      slowapi>=0.1.9
      sqlmodel>=0.0.24
      textual>=8.2.3
    ]
    venv.pip_install_and_link buildpath
  end

  test do
    assert_match "usage: ogham", shell_output("#{bin}/ogham --help")
  end
end
