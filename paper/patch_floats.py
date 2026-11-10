"""One-off: reduce main-body float pressure so figures and tables stop
drifting pages past the text that calls them."""
import io

p = "main.tex"
s = io.open(p, encoding="utf-8").read()

# \FloatBarrier stops a float escaping past its own section
s = s.replace(r"\usepackage{dblfloatfix}",
              "\\usepackage{dblfloatfix}\n\\usepackage[section]{placeins}")

# table1 is design description, not a result: move it out of the main body
before = s
s = s.replace("\\input{table1_design}\n", "", 1)
assert s != before, "table1_design not found in body"

s = s.replace("\\section{Prompts}\n\\label{app:prompts}",
              "\\section{Design Summary}\n\\label{app:design}\n"
              "\\input{table1_design}\n\n"
              "\\section{Prompts}\n\\label{app:prompts}")

# barriers at the two subsection boundaries whose floats were escaping
s = s.replace("\\subsection{Structured identifiers}",
              "\\FloatBarrier\n\\subsection{Structured identifiers}")
s = s.replace("\\subsection{Completion}",
              "\\FloatBarrier\n\\subsection{Completion}")

io.open(p, "w", encoding="utf-8").write(s)
print("patched main.tex")
