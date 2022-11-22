import warnings
from pathlib import Path
from MRdataset.utils import random_name
from MRdataset.config import CACHE_DIR, MRDS_EXT
from mrQA.run_subset import read_subset
from mrQA.run_merge import check_and_merge
from MRdataset.base import save_mr_dataset
from mrQA.utils import create_index, execute_local, list2txt, txt2list
import subprocess
import math


def parallel_dataset(data_root=None,
                     style='dicom',
                     name=None,
                     reindex=False,
                     include_phantom=False,
                     verbose=False,
                     metadata_root=None,
                     debug=False,
                     subjects_per_job=None,
                     submit_job=False,
                     conda_env=None):
    if debug and submit_job:
        raise AttributeError('Cannot debug when submitting jobs')
    if style != 'dicom':
        raise NotImplementedError(f'Expects dicom, Got {style}')

    if not Path(data_root).is_dir():
        raise OSError('Expected valid directory for --data_root argument,'
                      ' Got {0}'.format(data_root))
    data_root = Path(data_root).resolve()

    if not metadata_root:
        metadata_root = Path.home() / CACHE_DIR
        metadata_root.mkdir(exist_ok=True)

    if not Path(metadata_root).is_dir():
        raise OSError('Expected valid directory for --metadata_root argument,'
                      ' Got {0}'.format(metadata_root))
    metadata_root = Path(metadata_root).resolve()

    if name is None:
        warnings.warn(
            'Expected a unique identifier for caching data. Got NoneType. '
            'Using a random name. Use --name flag for persistent metadata',
            stacklevel=2)
        name = random_name()

    txt_path_list = create_index(data_root, metadata_root, name,
                                 reindex, subjects_per_job)

    all_batches_txt_filepath = metadata_root / (name+'_txt_files.txt')
    list2txt(path=all_batches_txt_filepath, list_=txt_path_list)

    processes = []
    for txt_filepath in txt_path_list:
        # create slurm script to call run_subset.py
        s_folderpath = metadata_root / f'scripts_{name}'
        s_folderpath.mkdir(parents=True, exist_ok=True)
        s_filename = s_folderpath / (txt_filepath.stem + '.sh')
        if not conda_env:
            env = 'mrqa' if submit_job else 'mrcheck'
        create_slurm_script(s_filename, name, metadata_root, txt_filepath,
                            env, subjects_per_job)
        output = run_single(debug, metadata_root, txt_filepath, reindex,
                            verbose, include_phantom, s_filename, submit_job)
        processes.append(output)
    if not submit_job:
        if not debug:
            exit_codes = [p.wait() for p in processes]
            check_and_merge(name, all_batches_txt_filepath)
    return


def run_single(debug, metadata_root, txt_filepath, reindex, verbose,
               include_phantom, s_filename, submit_job):
    # submit job or run with bash or execute with python
    if debug:
        partial_dataset = read_subset(metadata_root,
                                      txt_filepath, 'dicom',
                                      reindex, verbose,
                                      include_phantom)
        partial_dataset.set_cache_path()
        partial_dataset.is_complete = False
        save_filename = txt_filepath.with_suffix(MRDS_EXT)
        save_mr_dataset(save_filename, metadata_root, partial_dataset)
        return None
    elif not s_filename.with_suffix(MRDS_EXT).exists() or reindex:
        if not submit_job:
            return execute_local(s_filename)
        else:
            subprocess.call(['sbatch', s_filename])
            return


def create_slurm_script(filename, dataset_name, metadata_root,
                        txt_batch_filepath, env='mrqa',
                        num_subj_per_job=50):
    mem_reqd = 4096  # MB; fixed because we process only 1 subject at any time
    num_mins_per_subject = 1  # minutes
    num_hours = int(math.ceil(num_subj_per_job * num_mins_per_subject / 60))
    time_limit = 3 if num_hours < 3 else num_hours

    with open(filename, 'w') as fp:
        fp.writelines("\n".join([
            '#!/bin/bash',
            '#SBATCH -A med220005p',
            '#SBATCH -N 1',
            '#SBATCH -p RM-shared',
            f'#SBATCH --mem-per-cpu={mem_reqd}M #memory per cpu-core',
            f'#SBATCH --time={time_limit}:00:00',
            '#SBATCH --ntasks-per-node=1',
            f'#SBATCH --error={txt_batch_filepath.stem}.%J.err',
            f'#SBATCH --output={txt_batch_filepath.stem}.%J.out',
            '#SBATCH --mail-type=end          # send email when job ends',
            '#SBATCH --mail-type=fail         # send email if job fails',
            '#SBATCH --mail-user=harsh.sinha@pitt.edu',
            '#Clear the environment from any previously loaded modules',
            'module purge > /dev/null 2>&1',
            'source  ${HOME}/anaconda3/etc/profile.d/conda.sh',
            f'conda activate {env}',
            'mrpc_subset -m {} -name {} -b {}'.format(metadata_root,
                                                      dataset_name,
                                                      txt_batch_filepath),
            'date',
        ])
        )


if __name__ == '__main__':
    parallel_dataset(
        data_root='/media/sinhah/extremessd/ABCD-375/dicom-baseline',
        name='abcd-375',
        reindex=False,
        subjects_per_job=5,
        debug=True)