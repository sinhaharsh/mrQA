import shutil
import hypothesis.strategies as st
from hypothesis import given, settings, assume

from MRdataset import import_dataset
from MRdataset.simulate import make_compliant_test_dataset, \
    make_test_dataset
from compliance import check_compliance
from pathlib import Path
from collections import defaultdict


@settings(max_examples=50, deadline=None)
@given(st.integers(min_value=0, max_value=10),
       st.floats(allow_nan=False,
                 allow_infinity=False),
       st.integers(min_value=-10000000, max_value=10000000),
       st.floats(allow_nan=False,
                 allow_infinity=False))
def test_compliance_all_clean(num_subjects,
                              repetition_time,
                              echo_train_length,
                              flip_angle):
    """pass compliant datasets, and make sure library recognizes them as such"""
    dest_dir = make_compliant_test_dataset(num_subjects,
                                           repetition_time,
                                           echo_train_length,
                                           flip_angle)
    fake_mrd_dataset = import_dataset(dest_dir, include_phantom=True)
    checked_dataset = check_compliance(dataset=fake_mrd_dataset)

    sub_names_by_modality = defaultdict(list)
    for modality_pat in Path(dest_dir).iterdir():
        if modality_pat.is_dir() and ('.mrdataset' not in str(modality_pat)):
            for subject_path in modality_pat.iterdir():
                sub_names_by_modality[modality_pat.name].append(
                    subject_path.name)

    for modality in checked_dataset.modalities:
        percent_compliant = len(modality.compliant_subject_names) / len(
            modality.subjects)
        assert percent_compliant == 1.

        percent_non_compliant = len(modality.non_compliant_subject_names) / len(
            modality.subjects)
        assert percent_non_compliant == 0

        assert len(modality.non_compliant_subject_names) == 0
        assert len(modality.compliant_subject_names) == len(
            modality._children.keys())

        assert set(sub_names_by_modality[modality.name]) == set(
            modality.compliant_subject_names)
        assert len(modality.reasons_non_compliance) == 0

        assert modality.compliant
        assert not modality.is_multi_echo()

        for subject in modality.subjects:
            for session in subject.sessions:
                for run in session.runs:
                    assert not run.delta
                    assert run.params['tr'] == repetition_time
                    assert run.params[
                               'echo_train_length'] == echo_train_length
                    assert run.params['flip_angle'] == flip_angle
                    assert modality.reference[run.echo_time]['tr'] == \
                           repetition_time
                    assert modality.reference[run.echo_time][
                               'echo_train_length'] == \
                           echo_train_length
                    assert modality.reference[run.echo_time][
                               'flip_angle'] == flip_angle


def assert_list(list1, list2):
    if set(list1) == set(list2):
        if len(list1) == len(list2):
            return True
    return False


@settings(max_examples=100, deadline=None)
@given(st.lists(st.integers(min_value=0, max_value=3), min_size=15,
                max_size=15),
       st.floats(allow_nan=False, allow_infinity=False),
       st.integers(min_value=-10000000, max_value=10000000),
       st.floats(allow_nan=False, allow_infinity=False)
       )
def test_non_compliance(num_noncompliant_subjects,
                        repetition_time,
                        echo_train_length,
                        flip_angle):
    """pass non-compliant ds, and ensure library recognizes them as such"""
    assume(repetition_time != 200)
    assume(echo_train_length != 4000)
    assume(flip_angle != 80)

    fake_ds_dir, dataset_info = \
        make_test_dataset(num_noncompliant_subjects,
                          repetition_time,
                          echo_train_length,
                          flip_angle)
    mrd = import_dataset(fake_ds_dir, include_phantom=True)
    checked_dataset = check_compliance(dataset=mrd)

    # Check on disk, basically the truth
    sub_names_by_modality = defaultdict(list)
    for modality_path in Path(fake_ds_dir).iterdir():
        if modality_path.is_dir() and ('.mrdataset' not in str(modality_path)):
            for subject_path in modality_path.iterdir():
                sub_names_by_modality[modality_path.name].append(
                    subject_path.name)

    # Check if modalities are equal
    non_compliant_modality_names = [m for m in dataset_info if dataset_info[m]]
    assert assert_list(sub_names_by_modality.keys(),
                       checked_dataset._children.keys())

    assert assert_list(checked_dataset.non_compliant_modality_names,
                       non_compliant_modality_names)

    assert assert_list(checked_dataset.compliant_modality_names,
                       set(checked_dataset._children.keys()) - set(
                           non_compliant_modality_names))

    for modality in checked_dataset.modalities:
        # GT
        all_subjects = sub_names_by_modality[modality.name]
        non_compliant_subjects = dataset_info[modality.name]
        compliant_subjects = set(all_subjects) - set(non_compliant_subjects)

        # What did you parse
        assert assert_list(all_subjects, modality._children.keys())
        assert assert_list(non_compliant_subjects,
                           modality.non_compliant_subject_names)
        assert assert_list(compliant_subjects, modality.compliant_subject_names)

        # Check if reference has the right values
        echo_time = list(modality.reference.keys())[0]
        assert modality.reference[echo_time]['tr'] == 200
        assert modality.reference[echo_time]['echo_train_length'] == 4000
        assert modality.reference[echo_time]['flip_angle'] == 80

        for subject in modality.subjects:
            for session in subject.sessions:
                for run in session.runs:
                    if run.delta:
                        assert run.params['tr'] == repetition_time
                        assert run.params[
                                   'echo_train_length'] == echo_train_length
                        assert run.params['flip_angle'] == flip_angle
                    else:
                        assert run.params['tr'] == 200
                        assert run.params[
                                   'echo_train_length'] == 4000
                        assert run.params['flip_angle'] == 80


if __name__ == '__main__':
    test_non_compliance([0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 1.3, 53,
                        43)
    #     # test_compliance_all_clean(5, 0.0, echo_train_length=0, flip_angle=0)