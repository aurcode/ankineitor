import io
import os
import re
import PyPDF2
from typing import List, Union
from pptx import Presentation
import pandas as pd
import jieba.posseg as pseg

class TextExtractor:
    def __init__(self, uploaded_files: List[str], test: bool = False):
        self.test: bool = test
        self.uploaded_files: List[str] = uploaded_files
        self.text: Union[str, List] = []
        self.phrases: List[str] = []
        self.df: pd.DataFrame = pd.DataFrame([])

    def extract_text(self):
        for file_name, file_content in self.uploaded_files.items():
            if file_name.lower().endswith('.pdf'):
                self._extract_text_from_pdf(file_content)
            elif file_name.lower().endswith('.pptx'):
                self._extract_text_from_pptx(file_content)
            else:
                print(f'Unsupported file type: {file_name}')

        self.text = '。'.join(self.text)

    def _extract_text_from_pdf(self, file_content):
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        num_pages = len(pdf_reader.pages)
        if self.test:
            print("Test mode")
            max_page: int = 3
            page_count: int = 0
        for page_num in range(num_pages):
            page = pdf_reader.pages[page_num]
            page.extract_text()
            self.text.append(page.extract_text())
            self.phrases.append(page.extract_text())
            if self.test:
                page_count += 1
                if page_count == max_page:
                    break

    def _extract_text_from_pptx(self, file_content):
        pptx_file = io.BytesIO(file_content)
        presentation = Presentation(pptx_file)
        if self.test:
            print("Test mode")
            max_page: int = 3
            page_count: int = 0
        for slide in presentation.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        for run in paragraph.runs:
                            self.text.append(run.text)
            if self.test:
                page_count += 1
                if page_count == max_page:
                    break

    def printText(self, num = None):
        print('Len:', len(self.text))
        print(self.text[:num])

    def print_DF(self, head=True, num = 10):
        if head:
            print(self.df.head(num))
        else:
            print(self.df.tail(num))

    def _format_text(self,text:str, split_n: int):
        lines = text.split('\n')
        result = []
        current_line = ''

        for line in lines:
            if len(current_line) > split_n:
                result.append(current_line + line)
                current_line = ''
            elif len(line) <= split_n:
                result.append(line + '\n')
            else:
                current_line = line

        if current_line:
            result.append(current_line)
        formatted_text = ''.join(result)
        return formatted_text[:2000]


    def extract_phrases(self, split_n: int = 12, min_characters_n = 6):
        text_new = self._format_text(self.text, split_n)
        para = re.sub("([。！？\?])([^”'])", r"\1\n\2", text_new)
        para = re.sub("(\.{6})([^”'])", r"\1\n\2", para)
        para = re.sub("(\…{2})([^”'])", r"\1\n\2", para)
        para = re.sub("([。！？\?][”'])([^，。！？\?])", r'\1\n\2', para)
        para = para.rstrip()
        para = list(set(para.split("\n")))
        pattern = re.compile(r'[\u4e00-\u9fff]+')
        return [i for i in para
                if bool(re.search(pattern, i))
                if len(''.join(re.findall(pattern,i)))>=min_characters_n]

    @classmethod
    def read_files_to_uploaded(cls, file_paths):
        uploaded_files = {}
        for file_path in file_paths:
            file_name = os.path.basename(file_path)
            with open(file_path, 'rb') as file:
                file_content = file.read()
                uploaded_files[file_name] = file_content
        return uploaded_files

    def separated_chinese_characters(self, phrases=False):
        chinese_regex = r'[\u4E00-\u9FFF]+'
        chinese_characters = '。'.join(re.findall(chinese_regex, self.text))
        seg_list = list(pseg.cut(chinese_characters,use_paddle=True))
        df=pd.DataFrame(set(seg_list), columns=["hanzi", "part"])
        df=df[df['hanzi']!='。']
        df = df.groupby('hanzi')['part'].agg(lambda x: ', '.join(x)).reset_index()

        df_aux=pd.DataFrame(seg_list, columns=["hanzi", "part"])
        df_aux['frequency'] = df_aux['hanzi'].map(df_aux['hanzi'].value_counts())
        self.df = pd.merge(df, df_aux, on='hanzi', how='left')[['hanzi','part_x','frequency']].drop_duplicates(subset='hanzi').rename(columns={'part_x':'part'}).sort_values(by='frequency', ascending=False).reset_index(drop=True)

        if phrases:
            self.phrases = self.extract_phrases()

if __name__ == '__main__':
    uploaded_files = TextExtractor.read_files_to_uploaded(['./电路CLASSES.pdf'], )
    extractor = TextExtractor(uploaded_files, test=True)
    extractor.extract_text()
    print(extractor.phrases[:20])
    #print(extractor.extract_phrases())
    #extractor.separatedChineseCharacters()
    #extractor.printDF()