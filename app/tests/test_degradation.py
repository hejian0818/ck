"""Tests for advanced degradation modes."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.models.anchor import Anchor
from app.models.doc_models import DocumentSkeleton, SectionContent, SectionPlan
from app.models.graph_objects import File, Module, Relation, Symbol
from app.models.qa_models import RetrievalResult
from app.services.agents.doc_agent import DocAgent, DocLLMClient, SkeletonPlanner
from app.services.agents.metrics import Metrics
from app.services.agents.qa_agent import QAAgent
from app.services.retrieval.doc_retriever import DocRetriever, SectionRetrievalResult



class _QARepoStub:
    module = Module(id='M_mod', name='mod', path='mod', metadata={})
    file_obj = File(id='F_main', name='main.py', path='mod/main.py', module_id='M_mod', language='python', start_line=1, end_line=20)
    sym_a = Symbol(id='S_a', name='func_a', qualified_name='mod.func_a', type='function', signature='func_a()', file_id='F_main', module_id='M_mod', start_line=1, end_line=5, visibility='public', doc='')
    sym_b = Symbol(id='S_b', name='func_b', qualified_name='mod.func_b', type='function', signature='func_b()', file_id='F_main', module_id='M_mod', start_line=6, end_line=10, visibility='public', doc='')
    sym_c = Symbol(id='S_c', name='func_c', qualified_name='mod.func_c', type='function', signature='func_c()', file_id='F_main', module_id='M_mod', start_line=11, end_line=15, visibility='public', doc='')

    def find_span(self, file_path, line_start, line_end):
        return []

    def get_symbol_by_id(self, symbol_id):
        return {'S_a': self.sym_a, 'S_b': self.sym_b, 'S_c': self.sym_c}.get(symbol_id)

    def get_file_by_id(self, file_id):
        return self.file_obj if file_id == 'F_main' else None

    def get_module_by_id(self, module_id):
        return self.module if module_id == 'M_mod' else None

    def get_relations_by_source(self, source_id):
        return []

    def get_relations_by_target(self, target_id):
        return []

    def list_symbols_by_file(self, file_id):
        return [self.sym_a, self.sym_b]

    def list_files_by_module(self, module_id):
        return [self.file_obj]

    def find_symbols_by_name(self, name, limit=10):
        return []

    def find_files_by_name(self, name, limit=10):
        return []

    def find_modules_by_name(self, name, limit=10):
        return []


class _LLMStub:
    def generate(self, prompt):
        return 'stubbed'


class _DocRepoStub:
    module_a = Module(id='M_a', name='module_a', path='module_a', summary='', metadata={})
    module_b = Module(id='M_b', name='module_b', path='module_b', summary='', metadata={})
    file_a = File(id='F_a', name='a.py', path='module_a/a.py', module_id='M_a', language='python', summary='', start_line=1, end_line=10)

    def list_modules(self, repo_id):
        return [self.module_a, self.module_b]

    def list_relations(self, repo_id):
        return []

    def list_files_by_module(self, module_id):
        if module_id == 'M_a':
            return [self.file_a]
        return []

    def list_symbols_by_file(self, file_id):
        return []

    def list_symbols_by_module(self, module_id):
        return []

    def get_module_by_id(self, object_id):
        return {'M_a': self.module_a, 'M_b': self.module_b}.get(object_id)

    def get_file_by_id(self, object_id):
        return self.file_a if object_id == 'F_a' else None

    def get_symbol_by_id(self, object_id):
        return None

    def get_relations_by_source(self, source_id):
        return []

    def get_relations_by_target(self, target_id):
        return []

    def get_relation_by_id(self, relation_id):
        return None

    def get_repo_path(self, repo_id):
        return '/tmp/test_repo'


class _DocLLMStub:
    def generate(self, section, retrieval, prompt):
        return 'Content for ' + section.title + '.'


class QADegradationTests(unittest.TestCase):

    def setUp(self):
        self.repo = _QARepoStub()

    def _make_agent(self):
        return QAAgent(repository=self.repo, llm_client=_LLMStub())

    def test_partial_answer_when_some_objects_score_high(self):
        agent = self._make_agent()
        anchor = Anchor(level='symbol', source='name_match', confidence=0.9, module_id='M_mod')
        retrieval_result = RetrievalResult(
            anchor=anchor,
            current_object=self.repo.sym_a,
            related_objects=[self.repo.sym_b, self.repo.sym_c],
            object_scores={'S_a': 0.85, 'S_b': 0.3, 'S_c': 0.2},
        )
        metrics = Metrics(A=0.9, C=0.8, E=0.5, G=1.0, R=1.0)
        answer, suggestions = agent._build_degraded_answer(
            anchor=anchor, retrieval_result=retrieval_result,
            metrics=metrics, suggestions=[],
        )
        self.assertIn('S_a', answer)
        self.assertIn('[' + chr(0x4e0d) + chr(0x786e) + chr(0x5b9a) + ']', answer)
        self.assertIn('S_b', answer)
        self.assertTrue(suggestions)

    def test_multi_candidate_when_concentration_low(self):
        agent = self._make_agent()
        anchor = Anchor(level='none', source='none', confidence=0.3)
        retrieval_result = RetrievalResult(
            anchor=anchor,
            current_object=self.repo.sym_a,
            related_objects=[self.repo.sym_b, self.repo.sym_c],
            object_scores={'S_a': 0.4, 'S_b': 0.35, 'S_c': 0.3},
        )
        metrics = Metrics(A=0.3, C=0.3, E=0.3, G=1.0, R=0.5)
        answer, suggestions = agent._build_degraded_answer(
            anchor=anchor, retrieval_result=retrieval_result,
            metrics=metrics, suggestions=[],
        )
        self.assertIn('1.', answer)
        self.assertIn('S_a', answer)
        self.assertTrue(suggestions)

    def test_guided_followup_module_level(self):
        agent = self._make_agent()
        anchor = Anchor(level='module', source='name_match', confidence=0.7, module_id='M_mod')
        retrieval_result = RetrievalResult(
            anchor=anchor,
            current_object=self.repo.module,
            related_objects=[],
            object_scores={'M_mod': 0.5},
        )
        metrics = Metrics(A=0.7, C=0.8, E=0.4, G=1.0, R=1.0)
        answer, suggestions = agent._build_degraded_answer(
            anchor=anchor, retrieval_result=retrieval_result,
            metrics=metrics, suggestions=[],
        )
        self.assertIn('M_mod', answer)
        self.assertTrue(len(suggestions) >= 2)
        has_file_suggestion = any(chr(0x6587) + chr(0x4ef6) in s for s in suggestions)
        self.assertTrue(has_file_suggestion)


class DocDegradationTests(unittest.TestCase):

    def setUp(self):
        self.repo = _DocRepoStub()

    def test_low_confidence_labeling(self):
        retriever = DocRetriever(self.repo)
        agent = DocAgent(
            repository=self.repo,
            planner=SkeletonPlanner(self.repo),
            retriever=retriever,
            llm_client=_DocLLMStub(),
        )
        section_plan = SectionPlan(
            section_id='test-section', title='Test', level=1,
            section_type='summary', target_object_ids=[], description='A test.',
        )
        result = agent._generate_section(repo_id='repo_test', section=section_plan)
        if result.confidence < 0.3:
            self.assertIn('[Low Confidence]', result.content)

    def test_section_limit_enforcement(self):
        retriever = DocRetriever(self.repo)
        agent = DocAgent(
            repository=self.repo,
            planner=SkeletonPlanner(self.repo),
            retriever=retriever,
            llm_client=_DocLLMStub(),
        )
        many_sections = [
            SectionPlan(
                section_id='sec-' + str(i), title='Section ' + str(i), level=1,
                section_type='summary', target_object_ids=[], description='Desc.',
            )
            for i in range(60)
        ]
        skeleton = DocumentSkeleton(repo_id='repo_test', title='Test Doc', sections=many_sections)
        with patch('app.services.agents.doc_agent.settings') as mock_settings:
            mock_settings.DOC_MAX_SECTIONS = 5
            mock_settings.DOC_DIAGRAM_ENABLED = True
            mock_settings.DOC_RETRIEVAL_TOP_K = 10
            mock_settings.DOC_VECTOR_TOP_K = 5
            mock_settings.DOC_MODULE_SYMBOL_LIMIT = 8
            mock_settings.DOC_PLANNER_MAX_FILES_PER_MODULE = 3
            result = agent.generate('repo_test', skeleton=skeleton)
        self.assertEqual(len(result.sections), 5)
        self.assertEqual(result.metadata['section_count'], 5)

    def test_diagram_disabled(self):
        retriever = DocRetriever(self.repo)
        agent = DocAgent(
            repository=self.repo,
            planner=SkeletonPlanner(self.repo),
            retriever=retriever,
            llm_client=_DocLLMStub(),
        )
        section_plan = SectionPlan(
            section_id='overview', title='Overview', level=1,
            section_type='overview', target_object_ids=['M_a', 'M_b'], description='Overview.',
        )
        retrieval = SectionRetrievalResult(
            section=section_plan,
            objects=[self.repo.module_a, self.repo.module_b],
            relations=[], object_scores={'M_a': 0.8, 'M_b': 0.7},
        )
        with patch('app.services.agents.doc_agent.settings') as mock_settings:
            mock_settings.DOC_DIAGRAM_ENABLED = False
            diagrams = agent._generate_diagrams('repo_test', section_plan, retrieval)
        self.assertEqual(diagrams, [])


if __name__ == "__main__":
    unittest.main()
