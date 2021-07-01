deBug=True

if deBug:
    import sys
    import os
    sys.path.append(os.getcwd())
    from foo.fdjAnalyzePDF.fdjAnalyzePDF import AnalyzePDF

    if __name__ == "__main__":
        m_ss=AnalyzePDF()
        m_ss.analyzPDF("C:\\Users\\Administrator\\Downloads\\3333.pdf",debug=True)
        # m_ss.analyzPDF("/Users/lagel/Downloads/english.pdf",debug=True)
        # m_ss.ppt2json("/Users/lagel/Downloads/1114.pptx")

