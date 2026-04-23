class Ogham < Formula
  include Language::Python::Virtualenv

  desc "Minimal in-terminal chat app built with Textual"
  homepage "https://github.com/JRiggles/ogham-chat"
  license "MIT"
  head "https://github.com/JRiggles/ogham-chat.git", branch: "main"

  depends_on "python@3.12"

  def install
    venv = virtualenv_create(libexec, "python3.12")
    system libexec/"bin/pip", "install", buildpath
    bin.install_symlink libexec/"bin/ogham"
  end

  test do
    assert_match "usage: ogham", shell_output("#{bin}/ogham --help")
  end
end
