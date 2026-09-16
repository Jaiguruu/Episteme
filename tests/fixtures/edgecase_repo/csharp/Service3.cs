using System;

namespace Example.Gen
{
    public interface IHandler3
    {
        bool Handle(string payload);
    }

    public class Base3
    {
        protected string Name;
    }

    public class Service3 : Base3, IHandler3
    {
        public Service3(string name)
        {
            this.Name = name;
        }

        public bool Handle(string payload)
        {
            this.Validate(payload);
            return true;
        }

        private void Validate(string payload) { }
    }
}
