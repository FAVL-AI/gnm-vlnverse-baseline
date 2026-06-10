std_msgs/Header header
float32[] joint_positions      # 18 target joint positions (rad)
float32[] joint_torques        # 18 final torque commands (Nm)
bool cbf_intervened            # True if CBF modified the action
float32 cbf_h_min              # Minimum barrier function value
float32[] nominal_positions    # 18 original policy output (before CBF)
