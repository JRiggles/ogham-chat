class Ogham < Formula
  include Language::Python::Virtualenv

  desc "Minimal in-terminal chat app built with Textual"
  homepage "https://github.com/JRiggles/ogham-chat"
  url "https://github.com/JRiggles/ogham-chat/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "d5558cd419c8d46bdc958064cb97f963d1ea793866414c025906ec15033512ed"
  license "MIT"
  head "https://github.com/JRiggles/ogham-chat.git", branch: "main"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "usage: ogham", shell_output("#{bin}/ogham --help")
  end
end
