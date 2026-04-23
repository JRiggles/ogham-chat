class Ogham < Formula
  desc "Minimal in-terminal chat app built with Textual"
  homepage "https://github.com/JRiggles/ogham-chat"
  license "MIT"
  head "https://github.com/JRiggles/ogham-chat.git", branch: "main"

  depends_on "python@3.12"

  def install
    system Formula["python@3.12"].opt_bin/"python3.12", "-m", "venv", libexec
    system libexec/"bin/pip", "install", \
      "fastapi[standard]>=0.135.3", \
      "psycopg>=3.2.9", \
      "slowapi>=0.1.9", \
      "sqlmodel>=0.0.24", \
      "textual>=8.2.3"
    system libexec/"bin/pip", "install", "--no-deps", buildpath
    bin.install_symlink libexec/"bin/ogham"
  end

  test do
    assert_match "usage: ogham", shell_output("#{bin}/ogham --help")
  end
end
