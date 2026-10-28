"""The source and Full share this test selection; features are not coverage percentages.

Files remain named for their original regressions. Selection follows behaviour,
not a list copied into each new release. New tests must register their purpose.
"""
from pathlib import Path

# Hardware/runtime integrations are available through the same entry, explicitly.
# A Source checkout does not carry matching native Word binaries.
EXPLICIT_FEATURES = {'report_word','desktop_runtime'}

FEATURES = {
    'topic_links': ('Protected heading labels, Mermaid captions, scoped numbering and explicit native path links', 'topic_links_browser local_links_contract notebook_node'),
    'frontend_feedback': ('Native input shortcuts, bounded table sessions and project image path consistency', 'frontend_feedback_browser asset_paths_contract v1_feedback_contract report_workspace_contract block_commit_contract'),
    'numbering': ('Unified document numbering and editable mathematical clipboard content', '''numbering_v2_contract numbering_v2_node
        numbering_v2_browser:UnifiedNumbering.test_01_modes_and_formula_switch_share_objects
        numbering_v2_browser:UnifiedNumbering.test_02_new_formula_has_identity_without_insert_number_choice
        numbering_v2_browser:UnifiedNumbering.test_05_plain_objects_gain_identity_only_when_referenced
        numbering_v2_browser:UnifiedNumbering.test_06_formula_option_survives_archive_and_reading_pack'''),
    'desktop': ('Shared close/print adapter, offline core update/rollback and host integrity boundaries', 'desktop_contract desktop_node portable_contract native_picker release_contract'),
    'desktop_browser': ('Existing browser explicit exit still flushes the original draft and keeps failed closes open', 'maintenance_browser:MaintenanceExperience.test_browser_exit_flushes_latest_large_draft_and_refuses_failed_write'),
    'desktop_runtime': ('Explicit real Electron host save/close/failure/ownership/PDF/Word and final desktop payload', 'desktop_runtime'),
    'files': ('Direct Markdown files, scoped object tail input, explicit asset recycle cleanup and output-folder actions', '''
        markdown_file_contract markdown_file_browser
        block_commit_contract block_save_api_contract
        maintenance_contract:AssetCleanup
        maintenance_browser:MaintenanceExperience.test_asset_recycle_clear_requires_confirmation_and_preserves_live_assets
        maintenance_browser:MaintenanceExperience.test_export_toast_folder_action_uses_created_result_and_expires_cleanly
        maintenance_browser:MaintenanceExperience.test_pdf_export_uses_same_result_folder_action
        report_workspace_browser:ReportExperience.test_scoped_tail_object_allows_new_paragraphs_and_undo
        report_workspace_browser:ReportExperience.test_image_tail_enter_in_scoped_last_topic_and_whole_document
        report_workspace_browser:ReportExperience.test_reading_modules_and_human_filename
        report_workspace_browser:ReportExperience.test_scoped_edit_undo_preserves_hidden_notes_and_utf16_neighbors
        report_workspace_browser:ReportExperience.test_topic_first_heading_keeps_source_typography'''),
    'feedback': ('1.0 saved image objects, direct Word routing, reviewed origin sync, TOC and theme failure recovery', '''
        v1_feedback_contract v1_feedback_browser notebook_node v061_import_browser core_consistency_browser
        report_workspace_contract block_commit_contract'''),
    'maintenance': ('1.0 recovery/preflight/lifecycle/concurrency/DOM/CLI and shared configuration', '''
        maintenance_contract maintenance_browser maintenance_node report_workspace_contract report_workspace_browser
        source_index_node notebook_node core_consistency_contract distribution_contract pf131_contract
        interfaces_contract run_checks_contract release_contract block_commit_contract'''),
    'report_word': ('Explicit native Word component integration for import and the temporary report workflow; requires HRS_WORD_SUPPORT/PYTHON/PANDOC', '''report_workspace_word_browser word_import_browser
        numbering_v2_browser:UnifiedNumbering.test_03_mathml_mixed_paste_preserves_inline_math_and_table
        numbering_v2_browser:UnifiedNumbering.test_04_word_formula_numbers_and_reference_policy
        numbering_v2_browser:UnifiedNumbering.test_07_plain_markdown_figures_and_tables_use_native_word_numbers'''),
    'report_workspace': ('R7 real-project feedback: note/scope/scroll/save, report preparation and reading modules', '''
        report_workspace_contract report_workspace_browser notebook_node notebook_contract notebook_browser
        core_consistency_contract interfaces_contract run_checks_contract release_contract pf1310_math_browser
        heading_profile_browser:HeadingProfile.test_02_section_reference_uses_current_map_in_all_views_and_first_open
        preview_follow_browser:PreviewFollow.test_03_wheel_follow_keeps_running_with_editing_focus_and_source_changes
        word_footnotes_browser:FootnotesTables.test_01_table_refs_share_document_numbering_and_offline_navigation
        table_position_browser'''),
    'notebook': ('Free blank lines, source-bound H1 focus, archives and their render/scroll compatibility', '''
        report_workspace_browser:ReportExperience.test_topic_first_heading_keeps_source_typography
        notebook_node notebook_contract notebook_browser core_consistency_contract release_contract interfaces_contract run_checks_contract
        pf135_node source_index_node pf1310_math_browser v060_cli_browser memory_browser pf1310_rc2_browser pf1310_clipboard_browser table_position_browser
        heading_profile_browser:HeadingProfile.test_02_section_reference_uses_current_map_in_all_views_and_first_open
        heading_profile_browser:HeadingProfile.test_03_free_heading_toggle_persists_archive_and_engineering_forces_numbers
        document_search_browser:DocumentSearch.test_01_full_source_and_folded_object_are_located_without_changes
        document_search_browser:DocumentSearch.test_02_reading_search_spans_inline_nodes_and_ignores_caption_mirrors
        preview_follow_browser:PreviewFollow.test_01_quote_single_lines_paragraphs_and_explicit_break_share_offline_style
        preview_follow_browser:PreviewFollow.test_03_wheel_follow_keeps_running_with_editing_focus_and_source_changes
        word_footnotes_browser:FootnotesTables.test_01_table_refs_share_document_numbering_and_offline_navigation'''),
    'tables': ('Table structure, merged cells, alignment, title/layout, source/TSV/print', '''
        pf13_contract pf13_node pf13_browser pf131_contract pf131_node pf132_node
        pf132_browser pf134_style_contract pf134_browser pf135_browser
        v061_table_browser table_position_browser
        word_footnotes_browser:FootnotesTables.test_02_all_columns_center_is_one_undoable_edit_for_both_table_kinds'''),
    'source': ('Identity, UTF-16 ranges, references, literal code and semantic parity', '''
        pf133_contract pf133_node pf135_contract pf135_node pf136_node
        pf136_browser pf137_contract pf137_node source_index_node'''),
    'agent': ('Read-only Agent queries, explicit plan/apply and transactional refusal', '''
        pf131_contract pf133_contract pf135_contract pf137_contract
        block_commit_contract block_save_api_contract html_cli_contract'''),
    'html': ('Native HTML, safe tags/assets, archives, old reader trust, opt-in API', '''
        preview_follow_browser:PreviewFollow.test_01_quote_single_lines_paragraphs_and_explicit_break_share_offline_style
        pf13_contract pf132_browser pf137_programmatic_browser pf138_html_browser
        safe_html_contract reader_headings_contract v060_cli_browser html_cli_contract'''),
    'math': ('TeX delimiters, table/paragraph math, literal code, supplied article', '''
        pf132_browser pf133_browser pf133_contract pf133_node pf1310_math_browser'''),
    'theme': ('Canonical settings, six palettes, highlights and output identity', '''
        v060_contract v060_browser core_consistency_contract core_consistency_browser'''),
    'headings': ('Heading/profile rules, literal prefixes, TOC, section references', '''
        pf137_headings_browser pf139_profile_node pf139_profiles_browser
        rc2_output_contract heading_profile_browser'''),
    'editor': ('Selection, inline edits, undo/redo, quote paragraphs and scroll following', '''
        report_workspace_browser:ReportExperience.test_scoped_tail_object_allows_new_paragraphs_and_undo
        report_workspace_browser:ReportExperience.test_image_tail_enter_in_scoped_last_topic_and_whole_document
        report_workspace_browser:ReportExperience.test_topic_first_heading_keeps_source_typography
        pf1310_rc3_browser:ManualFeedback.test_04_nested_tasks_toggle_only_marker_and_support_undo_redo
        pf1310_rc3_browser:ManualFeedback.test_05_loose_tasks_keep_ordinary_markers_and_source
        pf1310_rc3_node
        v062_editor_browser r5_feedback_browser preview_follow_browser pf1310_rc2_browser'''),
    'objects': ('Object selection, clipboard identity/assets and draft recovery', '''
        rc2_clipboard_contract pf1310_clipboard_browser pf1310_rc2_browser word_clipboard_contract word_clipboard_browser
        report_workspace_browser:ReportExperience.test_scoped_tail_object_allows_new_paragraphs_and_undo
        report_workspace_browser:ReportExperience.test_image_tail_enter_in_scoped_last_topic_and_whole_document'''),
    'import': ('Relative local images, direct Markdown files, save failure protection and real manual/read packs', '''
        markdown_file_contract markdown_file_browser
        v061_import_contract v061_import_browser pf1310_import_browser
        rc3_save_contract pf1310_rc3_browser pf1310_rc3_node'''),
    'search': ('Full-source and rendered search, focus, folds, updates and source fidelity', '''
        document_search_browser table_position_browser'''),
    'word': ('HRS Word boundary, real local compiler, optional math, notes and references', '''
        word_export word_export_browser word_lite_browser word_footnotes_browser native_picker'''),
    'mermaid': ('Offline Mermaid syntax, saved drag layout, mathematical labels and bounded resources', 'mermaid_browser mermaid_node'),
    'docs': ('Real help HTTP/offline links, generated files and preserved source history', '''
        doc_layout_contract pf131_help_browser'''),
    'tooling': ('Test outcomes, selection, fixture cleanup, API documentation and release contracts', '''
        pf137_contract run_checks_contract test_system_contract interfaces_contract release_contract'''),
    'lifecycle': ('Window credentials, reconnect generations, request drain and control-frame boundary', 'portable_contract'),
    'memory': ('Current-document cache reuse, release across project loads and original-source protection', 'memory_browser'),
    'distribution': ('Installed command, generated Conda recipe, shared release identity and separate user state',
                     '''distribution_contract release_contract run_checks_contract test_system_contract
                        doc_layout_contract:DocumentationHTTP
                        doc_layout_contract:DocumentLayout.test_documented_ir_example_commands_succeed_without_source_changes'''),
}

# Existing Full commands remain accepted as aliases for declared current work.
ALIASES = {
    'core': ['theme', 'source', 'objects', 'headings'],
    'heading-profile': ['headings'], 'preview-follow': ['editor'],
    'editor-workflow': ['editor', 'search', 'word'],
    'table-position': ['search'], 'notes': ['word', 'tables'],
    'word-lite': ['word'], 'word-export': ['word'],
    'v062': ['editor'], 'v061': ['import', 'tables'],
    'v060': ['theme', 'import', 'html'], 'rc3': ['import', 'html'],
    'rc2': ['objects', 'agent', 'headings'],
}

GATES = {
    'conda_recipe': ('python', 'tools/build_conda_recipe.py'),
    'settings_generation': ('node', 'app/tools/build_settings.js'),
    'reader_bundle': ('node', 'app/tools/build_reader_bundle.js'),
    'readable_docs': ('node', 'app/tools/build_readable_docs.js'),
    'module_catalog': ('python', 'app/tools/audit_modules.py'),
    'documentation': ('python', 'app/tools/maintain_docs.py'),
}


def registered_tests():
    tests = {}
    for feature, (_, names) in FEATURES.items():
        for name in names.split():
            name, _, selector = name.partition(':')
            identifier = 'test_' + name
            item = tests.setdefault(identifier, {'id': identifier, 'features': [], 'feature_selectors': {}})
            if feature not in item['features']:
                item['features'].append(feature)
            choices = item['feature_selectors']
            if feature not in choices:
                choices[feature] = [selector] if selector else None
            elif choices[feature] is not None:
                choices[feature] = sorted(set(choices[feature] + [selector])) if selector else None
    for item in tests.values():
        identifier = item['id']
        item['path'] = 'tests/' + identifier + ('.js' if identifier.endswith('_node') else '.py')
        item['kind'] = ('browser' if identifier.endswith('_browser') else
                        'node' if identifier.endswith('_node') else 'contract')
        item['boundary'] = ('component-DOM' if identifier in ('test_pf135_browser', 'test_pf137_headings_browser')
                            else 'real-local-service' if item['kind'] == 'browser' else 'contract-or-unit')
        item['explicit_selection_required'] = set(item['features']) <= EXPLICIT_FEATURES
    return tests


def select_tests(source, groups, *, require_all=True):
    tests = registered_tests()
    unknown = set(groups) - set(FEATURES) - set(ALIASES) - {'contracts', 'browsers', 'generated', 'full'}
    if unknown:
        raise ValueError('Unknown test groups: ' + ', '.join(sorted(unknown)))
    features = {target for group in groups for target in ALIASES.get(group, [group])}
    selected = [item for item in tests.values() if set(item['features']) & features or
                not item['explicit_selection_required'] and (
                    'full' in features or
                    'contracts' in features and item['kind'] != 'browser' or
                    'browsers' in features and item['kind'] == 'browser')]
    if require_all:
        missing = [item['path'] for item in selected if not (Path(source) / item['path']).is_file()]
        if missing:
            raise ValueError('Selected tests missing: ' + ', '.join(missing))
    for item in selected:
        all_cases = ('full' in features or 'contracts' in features and item['kind'] != 'browser' or
                     'browsers' in features and item['kind'] == 'browser')
        # A module may contain both core and optional native integrations.
        # Default/full expands only its non-explicit feature selectors, rather
        # than promoting the whole module (and hidden native dependencies).
        reasons = [feature for feature in item['features'] if feature in features or
                   all_cases and feature not in EXPLICIT_FEATURES]
        choices = [item['feature_selectors'][feature] for feature in reasons]
        item['selectors'] = None if any(choice is None for choice in choices) else sorted({case for choice in choices for case in choice})
        item['selected_by'] = sorted(features) if all_cases else reasons
    return sorted(selected, key=lambda item: item['id'])


def execution_requirements(plan):
    tests=[test for entry in plan for test in entry['tests']]
    needs_word=any(test['id'] in {'test_word_export_browser','test_word_lite_browser','test_word_import_browser','test_report_workspace_word_browser'} or
                   test['id']=='test_word_footnotes_browser' and test.get('selectors') is None for test in tests)
    return ['native-word-components','word-test-environment'] if needs_word else []


def command_plan(source, node, python, groups, *, generated=True, batch=True):
    tests = select_tests(source, groups)
    result = []
    prefix = [str(python), '-X', 'utf8', '-B']
    def arguments(items):
        return [item['path'] + '::' + selector if selector else item['path']
                for item in items for selector in item['selectors'] or [None]]
    for kind in ('contract', 'node', 'browser'):
        items = [item for item in tests if item['kind'] == kind]
        if kind == 'contract' and items:
            result.append({'name': 'python_contracts', 'command': prefix + ['tools/run_python_tests.py', '--files'] +
                           arguments(items), 'tests': items})
        elif kind == 'browser' and batch:
            # Guarded unittest modules can share imports and one browser process.
            # Standalone scripts stay separate until their semantics are migrated.
            import ast
            batched, standalone = [], []
            for item in items:
                tree = ast.parse((Path(source) / item['path']).read_text('utf8'))
                # The CLI intentionally creates its own Playwright sessions.
                # It must remain a process boundary even when it uses unittest.
                safe = item['id'] != 'test_v060_cli_browser' and any(isinstance(node, ast.ClassDef) for node in tree.body)
                (batched if safe else standalone).append(item)
            if batched:
                result.append({'name': 'python_browsers', 'command': prefix + ['tools/run_python_tests.py', '--reuse-browser', '--files'] +
                               arguments(batched), 'tests': batched})
            result += [{'name': item['id'], 'command': prefix + [item['path']] + (item['selectors'] or []), 'tests': [item]} for item in standalone]
        else:
            result += [{'name': item['id'], 'command': ([str(node)] if kind == 'node' else prefix) + [item['path']],
                        'tests': [item]} for item in items]
    if generated:
        result += [{'name': name, 'command': ([str(node)] if tool == 'node' else prefix) + [path, '--check'],
                    'tests': [], 'boundary': 'generated-artifact'} for name, (tool, path) in GATES.items()]
    return result
